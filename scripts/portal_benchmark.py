"""Benchmark the running portal end to end: real HTTP calls to POST /api/patient-routing.

Unlike scripts/benchmark_step1.py (which calls the Step 1 code directly), this sends each gold
message through the same API the patient page uses (Step 1 -> Step 2 hospitals), measures the
latency the patient sees, and reads the real LLM calls (model, time, tokens, cost) and the
judge's decisions from logs/step1_trace.jsonl afterwards.

    # start the app first (README "Start the app"), then:
    PYTHONPATH=src .venv/Scripts/python.exe scripts/portal_benchmark.py --n 100 --spacing 15
    PYTHONPATH=src .venv/Scripts/python.exe scripts/portal_benchmark.py --report-only data/evaluation/portal_runs/<run>

Queries: all of step1_gold_core50 + an even sample of step1_gold_mediroute and step1_gold_gretel.
--spacing keeps a gap between requests (OpenRouter new accounts allow 20 requests/minute per
model; one patient request makes 2-4 LLM calls). Writes results.jsonl and report.html into
data/evaluation/portal_runs/<run>/ and copies the report to docs/evaluation/portal_benchmark_report.html.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import statistics
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import benchmark_step1 as bench  # noqa: E402

from mediroute.utils.paths import DATA_DIR, LOG_DIR, PROJECT_ROOT  # noqa: E402

TRACE = LOG_DIR / "step1_trace.jsonl"
RUNS = DATA_DIR / "evaluation" / "portal_runs"
DOC_REPORT = PROJECT_ROOT / "docs" / "evaluation" / "portal_benchmark_report.html"


def pick_queries(n: int) -> list[dict]:
    core = bench.load_gold("core50")
    rest = n - len(core)
    picks = core[:n]
    for name, share in (("mediroute", rest // 2), ("gretel", rest - rest // 2)):
        rows = bench.load_gold(name)
        if share > 0:
            step = len(rows) / share
            picks += [rows[int(i * step)] for i in range(share)]
    return picks[:n]


def run(base: str, queries: list[dict], spacing: float, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    health = requests.get(f"{base}/api/health", timeout=10).json()
    print("portal:", health, flush=True)
    with (out / "results.jsonl").open("a", encoding="utf-8") as handle:
        for i, g in enumerate(queries, 1):
            started = time.perf_counter()
            text = g["query"] + (f"\n\nReport: {g['report_text']}" if g.get("report_text") else "")
            try:
                r = requests.post(f"{base}/api/patient-routing", data={"requirement": text, "top_k": "5"}, timeout=600)
                body, status = r.json(), r.status_code
            except Exception as exc:  # timeout or connection error counts as a failure
                body, status = {"error": str(exc)}, 0
            ms = int((time.perf_counter() - started) * 1000)
            step1 = body.get("step1") or {}
            rec = body.get("recommendation_result") or {}
            row = {"gold_set": g["gold_set"], "query_id": g["query_id"], "http": status, "client_ms": ms,
                   "workflow_status": body.get("workflow_status"), "workflow_id": body.get("workflow_id"),
                   "step1_request_id": step1.get("request_id"), "decision": step1.get("decision"),
                   "specialty": step1.get("suggested_specialty"), "emergency": step1.get("emergency"),
                   "step2_status": rec.get("status"), "step2_count": rec.get("count", 0),
                   "hospitals": [h.get("hospital_name") for h in (rec.get("results") or [])[:5]]}
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            ok = row["specialty"] in {g["expected_specialty"], *g["alternatives"]}
            print(f"[{i}/{len(queries)}] {g['gold_set']} {g['query_id']} {row['decision']}/{row['specialty']} "
                  f"{'OK' if ok else 'expected ' + g['expected_specialty']} {ms} ms", flush=True)
            wait = spacing - (time.perf_counter() - started)
            if wait > 0 and i < len(queries):
                time.sleep(wait)


def read_trace(request_ids: set[str]) -> dict[str, dict]:
    by: dict[str, dict] = {r: {"llm": [], "votes": {}, "judge": None, "total_ms": None} for r in request_ids}
    with TRACE.open(encoding="utf-8") as handle:
        for line in handle:
            e = json.loads(line)
            rid = e.get("request_id")
            if rid not in by:
                continue
            t = by[rid]
            if e["stage"] == "llm_call" and e.get("purpose") or e["stage"] == "llm_call":
                t["llm"].append({"for": e.get("stage_for"), "ok": e.get("ok"), "ms": e.get("duration_ms"),
                                 "first_token_ms": e.get("first_token_ms"), "model": e.get("model_used") or e.get("model"),
                                 "cost": e.get("cost") or 0, "in": e.get("prompt_tokens") or 0,
                                 "out": e.get("output_tokens") or 0, "error": e.get("error"),
                                 "tried": e.get("models_tried")})
            elif e["stage"] == "vote":
                t["votes"][e.get("voter")] = [n for n, _ in e.get("top3") or []]
            elif e["stage"] == "judge":
                t["judge"] = {"status": e.get("status"), "final": e.get("final"), "candidates": e.get("candidates")}
            elif e["stage"] == "response":
                t["total_ms"] = e.get("total_ms")
    return by


def pct(values, q):
    values = sorted(v for v in values if v is not None)
    return values[min(len(values) - 1, int(round(q * (len(values) - 1))))] if values else None


def build_report(out: Path) -> Path:
    rows = [json.loads(l) for l in (out / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    gold = {(s, g["query_id"]): g for s in ("core50", "mediroute", "gretel") for g in bench.load_gold(s)}
    traces = read_trace({r["step1_request_id"] for r in rows if r["step1_request_id"]})
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))

    per_set: dict[str, list] = {}
    wrong_cases, judge_cases = [], []
    for r in rows:
        g = gold[(r["gold_set"], r["query_id"])]
        t = traces.get(r["step1_request_id"]) or {"llm": [], "votes": {}, "judge": None, "total_ms": None}
        ok_set = {g["expected_specialty"], *g["alternatives"]}
        ranked = list(dict.fromkeys(([r["specialty"]] if r["specialty"] else [])
                                    + [n for v in ("V1_lookup", "V2_llm") for n in t["votes"].get(v, [])]))[:3]
        r.update(ok=r["specialty"] in ok_set, answered=r["specialty"] is not None,
                 ndcg=bench.ndcg_at_k(ranked, g["expected_specialty"], g["alternatives"]),
                 step1_ms=t["total_ms"], llm=t["llm"], judge=t["judge"], expected=g["expected_specialty"],
                 query=g["query"])
        for key in ("all", r["gold_set"]):
            per_set.setdefault(key, []).append(r)
        if r["answered"] and not r["ok"]:
            wrong_cases.append(r)
        if t["judge"]:
            judge_cases.append(r)

    def summary(items):
        n = len(items)
        correct = sum(x["ok"] for x in items)
        lo, hi = bench.wilson(correct, n)
        return {"n": n, "acc": correct / n, "ci": (lo, hi), "ndcg": statistics.mean(x["ndcg"] for x in items),
                "wrong": sum(x["answered"] and not x["ok"] for x in items) / n,
                "asks": sum(not x["answered"] for x in items) / n}

    calls = [c for r in rows for c in r["llm"]]
    by_stage: dict[str, list] = {}
    for c in calls:
        by_stage.setdefault(c["for"] or "?", []).append(c)
    cost = sum(c["cost"] for c in calls)
    errors = [r for r in rows if r["http"] != 200]
    llm_fail = [c for c in calls if not c["ok"]]
    decisions = Counter(r["decision"] for r in rows)
    step2 = Counter(r["step2_status"] for r in rows)
    judge_status = Counter((r["judge"] or {}).get("status") for r in judge_cases)
    judge_right = sum(r["ok"] for r in judge_cases if (r["judge"] or {}).get("final"))
    judge_answered = sum(1 for r in judge_cases if (r["judge"] or {}).get("final"))

    e = html.escape
    def tr(cells, cls=""):
        return f"<tr{f' class={cls!r}' if cls else ''}>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"

    acc_rows = "".join(tr([e(k if k != "all" else f"All {len(rows)} queries"), s["n"], f"{s['acc']:.0%} <span class='m'>({s['ci'][0]:.0%}–{s['ci'][1]:.0%})</span>",
                           f"{s['ndcg']:.2f}", f"{s['wrong']:.0%}", f"{s['asks']:.0%}"], "win" if k == "all" else "")
                       for k, s in ((k, summary(v)) for k, v in sorted(per_set.items(), key=lambda kv: kv[0] != "all")))
    client = [r["client_ms"] for r in rows if r["http"] == 200]
    s1 = [r["step1_ms"] for r in rows if r["step1_ms"]]
    lat_rows = tr(["Patient waits (portal request, Step 1 + Step 2)", f"{pct(client, .5) / 1000:.1f} s", f"{pct(client, .95) / 1000:.1f} s", f"{max(client) / 1000:.1f} s"])
    lat_rows += tr(["Step 1 only", f"{pct(s1, .5) / 1000:.1f} s", f"{pct(s1, .95) / 1000:.1f} s", f"{max(s1) / 1000:.1f} s"])
    names = {"evidence_extraction": "LLM call: evidence", "specialty_vote": "LLM call: LLM voter", "judge": "LLM call: judge (each of 2)"}
    for stage, cs in sorted(by_stage.items()):
        ms_ = [c["ms"] for c in cs if c["ms"]]
        if ms_:
            lat_rows += tr([e(names.get(stage, stage)) + f" <span class='m'>({len(cs)} calls)</span>", f"{pct(ms_, .5) / 1000:.1f} s",
                            f"{pct(ms_, .95) / 1000:.1f} s", f"{max(ms_) / 1000:.1f} s"])
    models = Counter(c["model"] for c in calls)
    wrong_rows = "".join(tr([e(r["gold_set"]), e(r["query_id"]), e(r["query"][:90]), e(r["expected"]), e(r["specialty"]),
                             e(r["decision"])]) for r in wrong_cases) or tr(["–"] * 6)
    report = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Portal Benchmark</title>
<style>
:root {{ --bg:#f7f8f6; --card:#fff; --fg:#1b2321; --muted:#5d6b68; --line:#d8e0de; --head:#e6f0ee; --good-bg:#e3f3e8; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#121716; --card:#1b2321; --fg:#e4ebe9; --muted:#9aaba7; --line:#2f3b39; --head:#1f3330; --good-bg:#17331f; color-scheme:dark; }} }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:15px/1.55 "Segoe UI",system-ui,Arial,sans-serif; padding:28px max(16px,3vw) 56px; }}
main {{ max-width:980px; margin:0 auto; display:flex; flex-direction:column; gap:20px; }}
h1 {{ margin:0; font-size:1.7rem; }} h2 {{ margin:0 0 6px; font-size:1.15rem; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:16px 18px; }}
.scroll {{ overflow-x:auto; }} table {{ width:100%; border-collapse:collapse; font-size:.92rem; font-variant-numeric:tabular-nums; }}
th, td {{ padding:8px 10px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
th {{ background:var(--head); font-size:.85rem; }} tr.win td {{ background:var(--good-bg); font-weight:600; }}
.m, .muted {{ color:var(--muted); font-size:.85rem; font-weight:400; }} code {{ font-family:Consolas,monospace; font-size:.85em; }}
</style></head><body><main>
<header><h1>Portal benchmark: {len(rows)} real requests</h1>
<p class="muted">{e(meta['started'])} · each gold message sent to the running portal (<code>POST /api/patient-routing</code>: Step 1 → Step 2),
one request every {meta['spacing']:.0f} s. "Correct" = expected speciality or an accepted alternative; a clarification question counts as not correct.</p></header>

<section class="card"><h2>Setup</h2><div class="scroll"><table>
<tr><th>Part</th><th>Model / setting</th></tr>
{tr(["Evidence + LLM voter", e(meta.get('llm', ''))])}
{tr(["LLM judge (only on disagreements)", e(meta.get('judge', ''))])}
{tr(["Lookup voter", "TF-IDF + all-MiniLM-L6-v2 embeddings, local"])}
{tr(["Models seen in the LLM calls", e(', '.join(f'{m} ({n})' for m, n in models.items()))])}
</table></div></section>

<section class="card"><h2>Accuracy (Step 1)</h2><div class="scroll"><table>
<tr><th>Gold set</th><th>Queries</th><th>Correct (95% CI)</th><th>NDCG@3</th><th>Confidently wrong</th><th>Asks a question</th></tr>
{acc_rows}</table></div>
<p class="muted">Decisions: {e(', '.join(f'{k} {v}' for k, v in decisions.most_common()))}.
LLM judge used on {len(judge_cases)} requests: {e(', '.join(f'{k} {v}' for k, v in judge_status.most_common()))}; its accepted answers were right {judge_right} of {judge_answered}.</p></section>

<section class="card"><h2>Latency</h2><div class="scroll"><table>
<tr><th>What</th><th>Typical (p50)</th><th>Slow (p95)</th><th>Slowest</th></tr>
{lat_rows}</table></div>
<p class="muted">The evidence call and the LLM voter run in parallel for hosted models, so the patient waits about one call, plus the judge on disagreements.</p></section>

<section class="card"><h2>Cost and reliability</h2><div class="scroll"><table>
<tr><th>Item</th><th>Result</th></tr>
{tr(["LLM calls", f"{len(calls)} ({sum(c['in'] for c in calls):,} input + {sum(c['out'] for c in calls):,} output tokens)"])}
{tr(["Total cost", f"${cost:.4f} (≈ ${cost / max(1, len(rows)):.5f} per request)"])}
{tr(["Failed LLM calls", f"{len(llm_fail)}" + (f" — {e(str(llm_fail[0]['error'])[:120])}" if llm_fail else "")])}
{tr(["Failed portal requests (HTTP ≠ 200)", str(len(errors))])}
{tr(["Step 2 outcome", e(', '.join(f'{k} {v}' for k, v in step2.most_common()))])}
</table></div></section>

<section class="card"><h2>Answered with a wrong speciality ({len(wrong_cases)})</h2><div class="scroll"><table>
<tr><th>Set</th><th>ID</th><th>Message</th><th>Expected</th><th>Answered</th><th>How</th></tr>{wrong_rows}</table></div>
<p class="muted">Gold labels are team-written drafts awaiting doctor review; some "wrong" answers may be acceptable.</p></section>
<p class="muted">Raw results: <code>{e(str(out.relative_to(PROJECT_ROOT)))}/results.jsonl</code> · script: <code>scripts/portal_benchmark.py</code></p>
</main></body></html>"""
    (out / "report.html").write_text(report, encoding="utf-8")
    DOC_REPORT.write_text(report, encoding="utf-8")
    print(f"report: {DOC_REPORT}")
    return DOC_REPORT


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument("--spacing", type=float, default=15.0, help="seconds between request starts")
    parser.add_argument("--llm", default="", help="label for the report (model used by the portal)")
    parser.add_argument("--judge", default="openai/gpt-6-luna (OpenRouter)", help="label for the report")
    parser.add_argument("--report-only", type=Path)
    args = parser.parse_args()
    if args.report_only:
        build_report(args.report_only)
        return
    out = RUNS / datetime.now().strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    (out / "meta.json").write_text(json.dumps({"started": datetime.now().isoformat(timespec="seconds"), "n": args.n,
                                               "spacing": args.spacing, "llm": args.llm, "judge": args.judge,
                                               "base": args.base}, indent=2), encoding="utf-8")
    run(args.base, pick_queries(args.n), args.spacing, out)
    build_report(out)


if __name__ == "__main__":
    main()
