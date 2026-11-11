"""Step 1 POC: an LLM judge for disagreements between the lookup voter and the LLM voter.

Method 4 answers when the hybrid lookup voter and the LLM voter agree and asks the patient when
they disagree. Here a separate, stronger LLM (default GPT-6 Luna via OpenRouter, pinned, no
fallback, reasoning off) settles each disagreement, under guards that stop it from inventing
answers or evidence:

    closed choice     the JSON schema allows only the disputed specialities or "unclear"
    cited evidence    it must cite evidence lines (E1, E2 ...) built by code from the lookup list;
                      code checks each exists and that one maps to the chosen speciality
    real quote        its quote must be found in the patient text (verify_phrase)
    order swap        asked twice with the candidates in opposite order; both answers must match
    fail-safe         any failed check, "unclear", error or timeout -> ask the patient (as today)

Replays a finished scripts/benchmark_step1.py run (its LLM evidence and LLM votes), for two lookup
scorings of the app's lookup: M4 = plain hybrid voter, C3 = weak evidence half + best match per phrase.
Judge calls are cached in the run folder (judge_calls.jsonl), so a rerun never pays twice.

    PYTHONPATH=src .venv/Scripts/python.exe scripts/benchmark_step1_judge.py data/evaluation/results/<run> --dry-run
    PYTHONPATH=src .venv/Scripts/python.exe scripts/benchmark_step1_judge.py data/evaluation/results/<run> --limit 1
    PYTHONPATH=src .venv/Scripts/python.exe scripts/benchmark_step1_judge.py data/evaluation/results/<run>

Writes judge_calls.jsonl, report_judge.md and metrics_judge.json into the run folder.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import benchmark_step1 as bench  # noqa: E402
from benchmark_step1_replay import LookupVoter, load_trace  # noqa: E402

from mediroute.common.specialties import get_specialty  # noqa: E402
from mediroute.specialty_routing.step1.evidence import _tokens, verify_phrase  # noqa: E402
from mediroute.specialty_routing.step1.lookup import LookupIndex  # noqa: E402

JUDGE_MODEL = "openai/gpt-6-luna"
PROMPT_VERSION = "judge_v1"
EVIDENCE_K = 200          # how deep to look for the best entry of each candidate speciality
MIN_SEMANTIC, MIN_KEYWORD = 0.35, 0.15  # an evidence line must be at least loosely related
UNCLEAR = "unclear"
MIN_SECONDS_BETWEEN_CALLS = 3.6  # stays under OpenRouter's new-account limit of 20 requests/minute

PROMPT = """You help a hospital-discovery service decide which medical speciality a patient should search for.
Two methods disagree. Choose the ONE candidate speciality that best fits the patient's MAIN problem,
using only the patient's text and the evidence lines below. A diagnosis or a planned procedure
outweighs a symptom. If the text does not let you decide, answer "unclear".

Patient text:
\"\"\"{text}\"\"\"

Candidate specialities:
{candidates}

Evidence lines (phrase from the patient's text -> matching medical term in our list -> speciality):
{evidence}

Rules:
- "choice" must be one of the candidates above, or "unclear".
- "evidence" lists the IDs of the evidence lines that support your choice (at least one).
- "patient_quote" copies the exact words from the patient text that decided it.
- "reason" is one short sentence.
Answer with JSON only."""


def judge_schema(candidates: list[str], evidence_ids: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "choice": {"type": "string", "enum": candidates + [UNCLEAR]},
            "evidence": {"type": "array", "items": {"type": "string", "enum": evidence_ids or ["none"]}},
            "patient_quote": {"type": "string"},
            "reason": {"type": "string"},
        },
        "required": ["choice", "evidence", "patient_quote", "reason"],
    }


# ----------------------------------------------------------------------------- evidence lines
def evidence_lines(index: LookupIndex, phrases: list[str], candidates: list[str]) -> list[dict]:
    """For each evidence phrase and candidate speciality: the best-matching lookup entry of that
    speciality, if it is at least loosely related. Built by code, so every line is real."""
    lines = []
    for phrase in phrases:
        keyword = {e.entry_id: s for e, s in index.keyword_search(phrase, k=EVIDENCE_K)}
        semantic = index.embedding_search(phrase, k=EVIDENCE_K)
        best: dict[str, tuple[float, object]] = {}
        for entry, sem in semantic:
            if entry.specialty not in candidates:
                continue
            kw = keyword.get(entry.entry_id, 0.0)
            if sem < MIN_SEMANTIC and kw < MIN_KEYWORD:
                continue
            score = max(sem, kw)
            if score > best.get(entry.specialty, (0.0, None))[0]:
                best[entry.specialty] = (score, entry)
        for specialty in candidates:
            if specialty in best:
                entry = best[specialty][1]
                code = f" ({entry.source.split('_')[0].upper()} {entry.code})" if entry.code else ""
                lines.append({"phrase": phrase, "term": entry.text, "code": code.strip(), "specialty": specialty,
                              "score": round(best[specialty][0], 3)})
    for i, line in enumerate(lines, 1):
        line["id"] = f"E{i}"
    return lines


def build_prompt(text: str, candidates: list[str], lines: list[dict]) -> str:
    cand_text = "\n".join(f"- {c}: {getattr(get_specialty(c), 'description', '')}" for c in candidates)
    ev_text = "\n".join(f"{l['id']}: \"{l['phrase']}\" -> {l['term']} {l['code']} -> {l['specialty']}"
                        for l in lines) or "(none found)"
    return PROMPT.format(text=text.strip(), candidates=cand_text, evidence=ev_text)


# ----------------------------------------------------------------------------- guards
def check(parsed: dict, candidates: list[str], lines: list[dict], text: str) -> tuple[str | None, list[str]]:
    """Returns (accepted speciality or None, failed checks). None means: ask the patient."""
    failures = []
    choice = str(parsed.get("choice") or "").strip()
    if choice == UNCLEAR:
        return None, ["judge said unclear"]
    if choice not in candidates:
        failures.append("choice not a candidate")
    by_id = {l["id"]: l for l in lines}
    cited = [str(c) for c in parsed.get("evidence") or []]
    if not cited or any(c not in by_id for c in cited):
        failures.append("cited evidence missing or invented")
    elif not any(by_id[c]["specialty"] == choice for c in cited):
        failures.append("cited evidence does not support the choice")
    quote = str(parsed.get("patient_quote") or "")
    if not quote or not verify_phrase(quote, set(_tokens(text)))[0]:
        failures.append("quote not found in patient text")
    return (None, failures) if failures else (choice, [])


# ----------------------------------------------------------------------------- calls (cached)
class JudgeCaller:
    def __init__(self, cache_file: Path, model: str, dry_run: bool) -> None:
        self.cache_file, self.model, self.dry_run = cache_file, model, dry_run
        self.cache: dict[str, dict] = {}
        if cache_file.exists():
            for line in cache_file.read_text(encoding="utf-8").splitlines():
                rec = json.loads(line)
                if rec.get("ok"):  # failed calls (rate limit, timeout) are retried, never reused
                    self.cache[rec["key"]] = rec
        self.lock = threading.Lock()
        self.pace_lock = threading.Lock()
        self.next_call_at = 0.0
        self.client = None
        if not dry_run:
            from mediroute.specialty_routing.step1.ollama_client import OpenRouterClient
            self.client = OpenRouterClient(model=model)  # one model: no fallback

    def __call__(self, prompt: str, schema: dict) -> dict:
        key = hashlib.sha256(f"{self.model}|{PROMPT_VERSION}|{prompt}".encode("utf-8")).hexdigest()[:20]
        if key in self.cache:
            return self.cache[key]
        if self.dry_run:
            return {"key": key, "ok": False, "dry_run": True, "parsed": {}, "error": "dry run"}
        import time
        for attempt in range(6):
            with self.pace_lock:  # OpenRouter new accounts: 20 requests/minute per model
                wait = self.next_call_at - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                self.next_call_at = time.monotonic() + MIN_SECONDS_BETWEEN_CALLS
            self.client._model_down.clear()  # one pinned model: a 429 must not mark it down for good
            self.client._down_reason = ""
            call = self.client.generate_json(prompt, schema, purpose="step1_judge")
            if call.ok or "429" not in str(call.error):
                break
            time.sleep(15 * (attempt + 1))  # rate limited: back off and retry
        rec = {"key": key, "ok": call.ok, "parsed": call.parsed, "raw": call.raw_response, "error": call.error,
               "ms": call.duration_ms, "model_used": call.details.get("model_used"),
               "prompt_tokens": call.details.get("prompt_tokens"), "output_tokens": call.details.get("output_tokens"),
               "reasoning_tokens": call.details.get("reasoning_tokens"), "cost": call.details.get("cost")}
        with self.lock:
            self.cache[key] = rec
            with self.cache_file.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec


def judge_case(caller: JudgeCaller, index: LookupIndex, text: str, phrases: list[str], a: str, b: str) -> dict:
    candidates = [a, b]
    lines = evidence_lines(index, phrases, candidates)
    schema = judge_schema(candidates, [l["id"] for l in lines])
    first = caller(build_prompt(text, [a, b], lines), schema)
    second = caller(build_prompt(text, [b, a], lines), judge_schema([b, a], [l["id"] for l in lines]))
    out = {"candidates": candidates, "evidence_lines": lines, "calls": [first.get("key"), second.get("key")],
           "cost": sum(c.get("cost") or 0 for c in (first, second)),
           "tokens": sum((c.get("prompt_tokens") or 0) + (c.get("output_tokens") or 0) for c in (first, second))}
    if first.get("dry_run"):
        return {**out, "final": None, "status": "dry run", "prompt": build_prompt(text, [a, b], lines)}
    if not (first.get("ok") and second.get("ok")):
        return {**out, "final": None, "status": "call failed: " + str(first.get("error") or second.get("error"))[:120]}
    c1, f1 = check(first["parsed"], candidates, lines, text)
    c2, f2 = check(second["parsed"], candidates, lines, text)
    raw1, raw2 = first["parsed"].get("choice"), second["parsed"].get("choice")
    out.update({"choice_1": raw1, "choice_2": raw2, "failures": sorted(set(f1 + f2)),
                "reason": first["parsed"].get("reason", ""), "quote": first["parsed"].get("patient_quote", "")})
    if raw1 != raw2:
        return {**out, "final": None, "status": "order-swap flip"}
    if c1 is None:
        return {**out, "final": None, "status": "unclear" if raw1 == UNCLEAR else "check failed"}
    return {**out, "final": c1, "status": "accepted"}


# ----------------------------------------------------------------------------- main
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--model", default=JUDGE_MODEL)
    parser.add_argument("--dry-run", action="store_true", help="build prompts and evidence only, no API calls")
    parser.add_argument("--limit", type=int, default=0, help="judge only the first N disagreements (test)")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    run_dir = args.run_dir
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))

    index = LookupIndex()  # the app's lookup (CCSR mapping since 11 Nov 2026)
    index.ensure_embeddings()
    variants = {
        "M4": (index, LookupVoter(index, 1.0, False), "method 4 (hybrid lookup, plain scoring)"),
        "C3": (index, LookupVoter(index, 0.5, True), "C3 (hybrid lookup, weak evidence half + best match per phrase)"),
    }

    trace = load_trace(run_dir)
    gold = {(n, g["query_id"]): g for n in meta["sets"] for g in bench.load_gold(n)}
    records = [json.loads(l) for l in (run_dir / "predictions.jsonl").read_text(encoding="utf-8").splitlines()]

    cases = []  # (variant, set, gold, text, phrases, lookup top, llm top, base decision)
    for rec in records:
        ours, g = rec["systems"].get("OURS"), gold.get((rec["gold_set"], rec["query_id"]))
        if not ours or not g:
            continue
        t = trace.get(ours["request_id"], {})
        phrases, llm = t.get("phrases") or [], t.get("llm") or []
        text = g["query"] + (("\n\nReport:\n" + g["report_text"]) if g.get("report_text") else "")
        for key, (index, voter, _) in variants.items():
            h = voter.vote(phrases) if phrases else []
            cases.append({"variant": key, "set": rec["gold_set"], "gold": g, "text": text, "phrases": phrases,
                          "lookup": (h or [None])[0], "llm": (llm or [None])[0]})

    disagreements = [c for c in cases if c["lookup"] and c["llm"] and c["lookup"] != c["llm"]]
    if args.limit:
        disagreements = disagreements[: args.limit]
    print(f"{len(cases)} case-variants, {len(disagreements)} disagreements to judge "
          f"({'dry run' if args.dry_run else args.model})", flush=True)

    caller = JudgeCaller(run_dir / "judge_calls.jsonl", args.model, args.dry_run)

    def run(case):
        index = variants[case["variant"]][0]
        case["judge"] = judge_case(caller, index, case["text"], case["phrases"], case["lookup"], case["llm"])
        return case

    with ThreadPoolExecutor(max_workers=1 if args.dry_run else args.workers) as pool:
        for i, case in enumerate(pool.map(run, disagreements), 1):
            j = case["judge"]
            if i <= 3 or i % 25 == 0 or args.limit:
                print(f"[{i}/{len(disagreements)}] {case['variant']} {case['set']} {case['gold']['query_id']} "
                      f"lookup={case['lookup']} llm={case['llm']} -> {j['status']} {j.get('final') or ''} "
                      f"expected={case['gold']['expected_specialty']}", flush=True)
            if args.dry_run and i <= 1:
                print(j["prompt"])
    if args.dry_run or args.limit:
        for case in disagreements[:3]:
            print(json.dumps({k: case["judge"].get(k) for k in ("status", "final", "failures", "reason", "quote",
                                                                 "cost", "tokens")}, ensure_ascii=False))
        return

    # ------------------------------------------------------------------ score
    def acceptable(g):
        return {g["expected_specialty"], *g["alternatives"]}

    report = [f"# Step 1 POC: LLM judge on disagreements ({meta['run_id']})", "",
              f"Judge `{args.model}` (pinned, reasoning off, prompt `{PROMPT_VERSION}`), run twice per case with the "
              "candidate order swapped. Step 1 evidence and LLM votes: the Ollama run "
              f"(`{meta.get('llm')}`). Accuracy counts a clarification question as not correct.", ""]
    metrics = {}
    for vkey, (_, _, vlabel) in variants.items():
        report += [f"## {vlabel}", ""]
        metrics[vkey] = {}
        for set_name in meta["sets"]:
            rows = [c for c in cases if c["variant"] == vkey and c["set"] == set_name]
            n = len(rows)
            res = Counter()
            judged = [c for c in rows if "judge" in c]
            for c in rows:
                ok = acceptable(c["gold"])
                h, l = c["lookup"], c["llm"]
                agree = h if (h and l and h == l) or (h and not l) else None
                if agree == "General Medicine":
                    agree = None  # ask once before General Medicine (as in method 4)
                for rule, pred in (("T1 ask", agree), ("T2 LLM wins", agree or (l if h and l and h != l else None)),
                                   ("T3 lookup wins", agree or (h if h and l and h != l else None)),
                                   ("T5 judge", agree or (c.get("judge") or {}).get("final")),
                                   ("ceiling", agree or (h if h in ok else l if l in ok else None) if h and l and h != l else agree)):
                    res[(rule, "acc")] += pred in ok
                    res[(rule, "wrong")] += pred is not None and pred not in ok
                    res[(rule, "ask")] += pred is None
            status = Counter(c["judge"]["status"].split(":")[0] for c in judged)
            fails = Counter(f for c in judged for f in c["judge"].get("failures", []))
            acc_j = [c for c in judged if c["judge"].get("final")]
            right = sum(c["judge"]["final"] in acceptable(c["gold"]) for c in acc_j)
            metrics[vkey][set_name] = {"n": n, "disagreements": len(judged), "status": dict(status),
                                       "failures": dict(fails), "judge_answered": len(acc_j), "judge_right": right,
                                       "rules": {f"{r}|{m}": v for (r, m), v in res.items()}}
            report += [f"### {set_name} (n={n}, disagreements {len(judged)})", "",
                       "| Tie-break | Accuracy | Confidently wrong | Asks |", "|---|---|---|---|"]
            for rule in ("T1 ask", "T2 LLM wins", "T3 lookup wins", "T5 judge", "ceiling"):
                label = {"T5 judge": "**T5 LLM judge (guarded)**", "ceiling": "Perfect judge (ceiling)"}.get(rule, rule)
                report.append(f"| {label} | {res[(rule, 'acc')] / n:.0%} | {res[(rule, 'wrong')] / n:.0%} | "
                              f"{res[(rule, 'ask')] / n:.0%} |")
            report += ["", f"Judge on {len(judged)} disagreements: answered {len(acc_j)}, right {right}"
                       + (f" ({right / len(acc_j):.0%} of its answers)" if acc_j else "")
                       + f"; outcomes {dict(status)}; failed checks {dict(fails) or 'none'}", ""]

    all_judged = [c for c in cases if "judge" in c]
    total_cost = sum(caller.cache[k].get("cost") or 0 for k in {k for c in all_judged for k in c["judge"]["calls"] if k})
    calls = [caller.cache[k] for k in {k for c in all_judged for k in c["judge"]["calls"] if k}]
    report += ["## Hallucination guards and cost (all variants)", "",
               f"- Judge calls: {len(calls)} (failed: {sum(not c.get('ok') for c in calls)}); "
               f"reasoning tokens: {sum(c.get('reasoning_tokens') or 0 for c in calls)}",
               f"- Order-swap flips: {sum(c['judge']['status'] == 'order-swap flip' for c in all_judged)} of {len(all_judged)}",
               f"- Failed checks: {dict(Counter(f for c in all_judged for f in c['judge'].get('failures', [])))}",
               f"- Cost: ${total_cost:.4f} for {sum((c.get('prompt_tokens') or 0) + (c.get('output_tokens') or 0) for c in calls)} tokens", ""]
    wrong = [c for c in all_judged if c["judge"].get("final") and c["judge"]["final"] not in acceptable(c["gold"])]
    if wrong:
        report += ["## Judge answered wrongly", "", "| Variant | ID | Expected | Judge | Other candidate | Quote | Reason |",
                   "|---|---|---|---|---|---|---|"]
        for c in wrong:
            j = c["judge"]
            other = [x for x in j["candidates"] if x != j["final"]][0]
            report.append(f"| {c['variant']} | {c['gold']['query_id']} | {c['gold']['expected_specialty']} | {j['final']} | "
                          f"{other} | {j.get('quote', '')[:50]} | {j.get('reason', '')[:90]} |")
    (run_dir / "report_judge.md").write_text("\n".join(report), encoding="utf-8")
    (run_dir / "metrics_judge.json").write_text(json.dumps({"model": args.model, "prompt_version": PROMPT_VERSION,
                                                            "cost_usd": total_cost, "variants": metrics}, indent=2),
                                                encoding="utf-8")
    with (run_dir / "judge_cases.jsonl").open("w", encoding="utf-8") as handle:
        for c in all_judged:
            handle.write(json.dumps({"variant": c["variant"], "set": c["set"], "query_id": c["gold"]["query_id"],
                                     "lookup": c["lookup"], "llm": c["llm"], **c["judge"]}, ensure_ascii=False) + "\n")
    print("\n".join(report))


if __name__ == "__main__":
    main()
