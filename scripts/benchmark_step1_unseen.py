"""Step 1 on unseen data: today's judge vs F1 (boundaries in the judge prompt) vs F1 + a stronger judge.

    PYTHONPATH=src python scripts/benchmark_step1_unseen.py --set new --configs base,f1,f1_gemini,f1_terra
    PYTHONPATH=src python scripts/benchmark_step1_unseen.py --set heldout --configs base,<winner>
    PYTHONPATH=src python scripts/benchmark_step1_unseen.py --report

Result (12 Nov 2026): F1 and F2 gave no gain on unseen data, so they were REVERTED from the app;
only "base" (today's judge) can run now. The F1/F2 results stay in data/evaluation/step1_unseen/
(new_f1*.jsonl); rerunning them needs the judge_v2 prompt and the judge reasoning-effort option back.

Runs the app's real Step 1 pipeline in-process (evidence + LLM voter on GPT-6 Luna, lookup voter, judge).
Every LLM call is cached on disk by (model, prompt, schema), so configurations share the voter calls and
only changed judge calls are paid. A hard budget (--budget, default $1.50) covers the test-set
generation too; the run stops before spending more.

Sets
  new      data/evaluation/step1_gold_unseen.csv (written by a model MediRoute does not use)
  heldout  the mediroute (59) and gretel (100, evenly sampled) cases never used in the portal test
Scoring
  one turn      the first answer: correct / confidently wrong / asked
  right outcome correct, or asked on a case marked "expects clarification"
  after answer  when the app asks, the simulated patient answers the body-area question once
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import benchmark_step1 as bench  # noqa: E402
import portal_benchmark as portal  # noqa: E402

from mediroute.common.specialties import mapping_rules  # noqa: E402
from mediroute.specialty_routing.step1.judge import LLMJudge  # noqa: E402
from mediroute.specialty_routing.step1.lookup import LookupIndex  # noqa: E402
from mediroute.specialty_routing.step1.ollama_client import LLMCall, OpenRouterClient  # noqa: E402
from mediroute.specialty_routing.step1.pipeline import Step1Input, Step1Pipeline  # noqa: E402
from mediroute.utils.paths import DATA_DIR, PROJECT_ROOT  # noqa: E402

OUT = DATA_DIR / "evaluation" / "step1_unseen"
CACHE = OUT / "llm_cache.jsonl"
GEN_LOG = OUT / "generation_calls.jsonl"
NEW_SET = DATA_DIR / "evaluation" / "step1_gold_unseen.csv"
VOTER_MODEL = "openai/gpt-6-luna"
CONFIGS = {  # name -> (judge model, judge prompt, reasoning effort, label)
    "base": ("openai/gpt-6-luna", "judge_v1", None, "Today: GPT-6 Luna judge"),
    "f1": ("openai/gpt-6-luna", "judge_v2", None, "F1: boundaries in the judge prompt"),
    "f1_gemini": ("google/gemini-4-carbon", "judge_v2", "low", "F1 + F2: Gemini 4 Carbon judge"),
    "f1_terra": ("openai/gpt-6.1-terra", "judge_v2", None, "F1 + F2: GPT-6.1 Terra judge"),
}
GAP_S = 3.2  # OpenRouter new account: 20 requests/minute per model


class Budget:
    def __init__(self, limit: float):
        self.limit, self.lock = limit, threading.Lock()
        self.spent = sum(float(json.loads(l).get("cost") or 0) for path in (GEN_LOG, CACHE) if path.exists()
                         for l in path.read_text(encoding="utf-8").splitlines() if l.strip())

    def add(self, cost: float):
        with self.lock:
            self.spent += cost


class CachedClient:
    """generate_json with an on-disk cache, per-model pacing and a shared budget."""
    _cache: dict[str, dict] = {}
    _lock = threading.Lock()
    _next: dict[str, float] = defaultdict(float)

    def __init__(self, model: str, budget: Budget, effort: str | None = None):
        self.inner = OpenRouterClient(model=model, reasoning_effort=effort)
        self.model, self.budget = model, budget
        self.provider, self.parallel_calls, self.needs_priming = "openrouter", True, False
        if not CachedClient._cache and CACHE.exists():
            for line in CACHE.read_text(encoding="utf-8").splitlines():
                rec = json.loads(line)
                if rec.get("ok"):
                    CachedClient._cache[rec["key"]] = rec

    def status(self, force: bool = False):
        return self.inner.status(force)

    def warm_up(self):
        pass

    def generate_json(self, prompt: str, schema: dict, purpose: str) -> LLMCall:
        key = hashlib.sha256(f"{self.model}|{prompt}|{json.dumps(schema, sort_keys=True)}".encode()).hexdigest()[:24]
        hit = CachedClient._cache.get(key)
        if hit:
            return LLMCall(True, parsed=hit["parsed"], raw_response=hit.get("raw", ""),
                           details={"purpose": purpose, "model": self.model, "cached": True, "cost": 0.0})
        if self.budget.spent >= self.budget.limit:
            return LLMCall(False, error="budget reached", details={"purpose": purpose, "model": self.model})
        for attempt in range(5):
            with CachedClient._lock:
                wait = CachedClient._next[self.model] - time.monotonic()
                CachedClient._next[self.model] = max(time.monotonic(), CachedClient._next[self.model]) + GAP_S
            if wait > 0:
                time.sleep(wait)
            self.inner._model_down.clear()
            self.inner._down_reason = ""
            call = self.inner.generate_json(prompt, schema, purpose)
            if call.ok or "429" not in str(call.error):
                break
            time.sleep(15 * (attempt + 1))
        cost = float((call.details or {}).get("cost") or 0)
        self.budget.add(cost)
        rec = {"key": key, "ok": call.ok, "model": self.model, "purpose": purpose, "parsed": call.parsed,
               "raw": call.raw_response, "cost": cost, "ms": call.duration_ms, "error": call.error}
        with CachedClient._lock:
            OUT.mkdir(parents=True, exist_ok=True)
            with CACHE.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if call.ok:
                CachedClient._cache[key] = rec
        return call


# ------------------------------------------------------------------------------------- sets
def body_area_for(specialty: str) -> str:
    for rule in mapping_rules("body_area"):
        if specialty in rule.specialties:
            return rule.value
    return "Other / not sure"


def load_set(name: str) -> list[dict]:
    if name == "new":
        rows = list(csv.DictReader(NEW_SET.open(encoding="utf-8")))
        for r in rows:
            r["ok"] = [r["expected_specialty"], *[a for a in r["acceptable_alternatives"].split(";") if a]]
            r["expects_q"] = r["expects_clarification"] == "yes"
        return rows
    used = {(g["gold_set"], g["query_id"]) for g in portal.pick_queries(100)}
    rows = []
    for s in ("mediroute", "gretel"):
        unseen = [g for g in bench.load_gold(s) if (s, g["query_id"]) not in used]
        if s == "gretel":  # 100, evenly over the 22 diagnoses
            by = defaultdict(list)
            for g in unseen:
                by[g["case_type"]].append(g)
            picked, i = [], 0
            while len(picked) < 100 and any(by.values()):
                for k in sorted(by):
                    if by[k] and len(picked) < 100:
                        picked.append(by[k].pop(0))
            unseen = picked
        for g in unseen:
            rows.append({"query_id": f"{s}:{g['query_id']}", "query": g["query"], "expected_specialty": g["expected_specialty"],
                         "ok": [g["expected_specialty"], *g["alternatives"]], "case_type": g.get("case_type", ""),
                         "expects_q": (g.get("case_type") == "vague"),
                         "body_area_answer": body_area_for(g["expected_specialty"])})
    return rows


# ------------------------------------------------------------------------------------- run
def run_case(pipe: Step1Pipeline, case: dict) -> dict:
    t0 = time.perf_counter()
    first = pipe.analyze(Step1Input(text=case["query"]))
    out = {"id": case["query_id"], "decision1": first["decision"], "spec1": first["suggested_specialty"],
           "ms1": int((time.perf_counter() - t0) * 1000)}
    final = first
    if first["decision"] == "clarification_required":
        final = pipe.analyze(Step1Input(text=case["query"], clarification={"body_area": case["body_area_answer"]},
                                        clarification_round=1, parent_request_id=first["request_id"]))
    out.update(decision2=final["decision"], spec2=final["suggested_specialty"],
               shortlist=[x["name"] for x in ((final.get("user_choice") or {}).get("shortlist") or [])])
    return out


def score(case: dict, r: dict) -> dict:
    asked1 = r["spec1"] is None
    ok1 = r["spec1"] in case["ok"]
    ok2 = r["spec2"] in case["ok"]
    return {"correct": ok1, "wrong": (not asked1) and not ok1, "asked": asked1,
            "right_outcome": ok1 or (asked1 and case["expects_q"]),
            "correct_after": ok2, "wrong_after": r["spec2"] is not None and not ok2,
            "open_after": r["spec2"] is None,
            "in_shortlist": r["spec2"] is None and any(s in case["ok"] for s in r["shortlist"])}


def run_config(set_name: str, cases: list[dict], cfg: str, budget: Budget, index: LookupIndex) -> Path:
    model, prompt, effort, _ = CONFIGS[cfg]
    if prompt != "judge_v1":
        raise SystemExit(f"{cfg}: the judge_v2 prompt (F1) was reverted from the app; see the module docstring")
    voter = CachedClient(VOTER_MODEL, budget)
    pipe = Step1Pipeline(index=index, client=voter,
                         judge=LLMJudge(client=CachedClient(model, budget, effort), index=index))
    path = OUT / f"{set_name}_{cfg}.jsonl"
    done = {json.loads(l)["id"] for l in path.read_text(encoding="utf-8").splitlines()} if path.exists() else set()
    for i, case in enumerate(cases, 1):
        if case["query_id"] in done:
            continue
        if budget.spent >= budget.limit:
            print(f"STOP: budget ${budget.spent:.3f} >= ${budget.limit}")
            break
        r = run_case(pipe, case)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"[{set_name} {cfg} {i}/{len(cases)}] {case['query_id']} {r['decision1']}/{r['spec1']} -> {r['spec2']} "
              f"(exp {case['expected_specialty']}) · spent ${budget.spent:.3f}", flush=True)
    return path


def report() -> None:
    lines = [f"# Step 1 on unseen data ({datetime.now():%d %b %Y %H:%M})", ""]
    summary = {}
    for set_name in ("new", "heldout"):
        cases = {c["query_id"]: c for c in load_set(set_name)} if (set_name != "new" or NEW_SET.exists()) else {}
        rows = []
        for cfg, (model, prompt, effort, label) in CONFIGS.items():
            path = OUT / f"{set_name}_{cfg}.jsonl"
            if not path.exists():
                continue
            res = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]
            res = [r for r in res if r["id"] in cases]
            if len(res) < len(cases):
                label += f" (partial {len(res)}/{len(cases)})"
            sc = [score(cases[r["id"]], r) for r in res]
            n = len(sc) or 1
            m = {k: sum(s[k] for s in sc) / n for k in sc[0]} if sc else {}
            judged = sum(r["decision1"] == "judge" for r in res)
            ms = sorted(r["ms1"] for r in res)
            m.update(n=len(sc), judge_share=judged / n, p50_ms=ms[len(ms) // 2] if ms else None)
            summary[f"{set_name}:{cfg}"] = m
            rows.append(f"| {label} | {len(sc)} | {m['correct']:.0%} | {m['wrong']:.0%} | {m['asked']:.0%} | "
                        f"**{m['right_outcome']:.0%}** | **{m['correct_after']:.0%}** | {m['wrong_after']:.0%} | "
                        f"{m['open_after']:.0%} ({m['in_shortlist']:.0%} in list) |")
        if rows:
            lines += [f"## {set_name}", "", "| Config | n | Correct (1 turn) | Confidently wrong | Asked | Right outcome | "
                      "Correct after 1 answer | Wrong after | Still open |", "|---|---|---|---|---|---|---|---|---|", *rows, ""]
    spent = Budget(0).spent
    lines.append(f"Spend so far (generation + benchmark): ${spent:.3f}")
    (OUT / "report.md").write_text("\n".join(lines), encoding="utf-8")
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print("\n".join(lines))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["new", "heldout"])
    ap.add_argument("--configs", default="base,f1,f1_gemini,f1_terra")
    ap.add_argument("--budget", type=float, default=1.50)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()
    if args.report:
        report()
        return
    budget = Budget(args.budget)
    cases = load_set(args.set)[: args.limit or None]
    index = LookupIndex()
    for cfg in args.configs.split(","):
        run_config(args.set, cases, cfg.strip(), budget, index)
    report()


if __name__ == "__main__":
    main()
