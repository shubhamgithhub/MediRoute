"""End-to-end hospital benchmark through the running portal: patient text -> Step 1 -> Step 2 -> P/R/NDCG@K.

Each query of data/evaluation/step2_gold.csv is sent to POST /api/patient-routing exactly as the patient
page sends it (text + preferred city/state). Step 1 picks the speciality (and the procedures Step 2 uses)
from the text; nothing from the gold row is given to the portal except the location the patient types.
The hospitals the patient sees are scored against the gold need (gold speciality + procedure), so a wrong
Step 1 speciality costs the ranking, as it would cost the patient.

Simulated patient (favourable by construction, the same rule as scripts/portal_benchmark.py):
    body-area question  -> answers the area of the gold speciality (one round)
    speciality list     -> picks the gold speciality only if it is in the suggested shortlist, else gives up
    location question   -> no hospitals (scored 0)

    # start the app first (README "Start the app"), then:
    PYTHONPATH=src .venv/Scripts/python.exe scripts/portal_hospital_benchmark.py run --spacing 12
    PYTHONPATH=src .venv/Scripts/python.exe scripts/portal_hospital_benchmark.py pool  <run>   # ungraded pairs
    PYTHONPATH=src .venv/Scripts/python.exe scripts/step2_draft_grades.py --budget 0.15        # grade them
    PYTHONPATH=src .venv/Scripts/python.exe scripts/portal_hospital_benchmark.py score <run> [--judged-only]

Relevance and metrics are those of scripts/eval_step2.py (grades 0-3 from the hospitals' websites, 0 outside
the patient's area; relevant = grade >= 2). Two reference rows use the same grades: the offline engine with the
gold speciality and procedure (oracle Step 1) and B0 random among eligible hospitals.
Output: data/evaluation/portal_runs/<run>_hospitals/ results.jsonl, trace.jsonl, metrics.json, report.md
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eval_step2 as ev  # noqa: E402
from portal_benchmark import RUNS, copy_trace, post, simulated_answer  # noqa: E402

from mediroute.evaluation import ranking_metrics as rm  # noqa: E402
from mediroute.utils.paths import PROJECT_ROOT  # noqa: E402

TOP_K = 20        # asked from the portal; the patient sees the first 5, --judged-only condenses the 20
SHOWN = 5
MAX_FOLLOW_UPS = 2


# --------------------------------------------------------------------------- run

def ask(base: str, q: dict, extra: dict | None = None) -> tuple[dict, int, int]:
    data = {"requirement": q["patient_text"], "top_k": str(TOP_K)}
    if q["preferred_city"]:
        data["preferred_city"] = q["preferred_city"]
    if q["preferred_state"]:
        data["preferred_state"] = q["preferred_state"]
    return post(base, {**data, **(extra or {})})


def run_one(base: str, q: dict, spacing: float, out: Path) -> dict:
    """One patient search, with the simulated patient's follow-up answers. Returns the result row."""
    turns, body, round_no = [], {}, 0
    extra: dict = {}
    for _ in range(1 + MAX_FOLLOW_UPS):
        started = time.perf_counter()
        body, status, ms = ask(base, q, extra)
        step1 = body.get("step1") or {}
        turn = {"http": status, "client_ms": ms, "workflow_status": body.get("workflow_status"),
                "clarification_type": body.get("clarification_type"), "request_id": step1.get("request_id"),
                "decision": step1.get("decision"), "specialty": step1.get("suggested_specialty"),
                **({"sent": {k: v for k, v in extra.items() if k != "parent_request_id"}} if extra else {})}
        turns.append(turn)
        copy_trace(turn["request_id"], out)
        if status != 200 or body.get("workflow_status") != "waiting_for_clarification":
            break
        if body.get("clarification_type") == "location":
            turn["gave_up"] = "location question"
            break
        round_no += 1
        parent = {"parent_request_id": turn["request_id"] or "", "clarification_round": str(round_no)}
        if turn["decision"] == "clarification_required":
            extra = {**parent, "clarification_body_area": simulated_answer({"expected_specialty": q["specialty"]})}
        elif turn["decision"] == "needs_user_choice":
            shortlist = ((step1.get("user_choice") or {}).get("suggested_first")) or []
            if q["specialty"] not in shortlist:
                turn["gave_up"] = f"gold speciality not in the shortlist {shortlist}"
                break
            extra = {**parent, "selected_specialty": q["specialty"]}
        else:
            turn["gave_up"] = "unknown clarification"
            break
        time.sleep(max(0.0, spacing - (time.perf_counter() - started)))

    rec = body.get("recommendation_result") or {}
    shown = [*(rec.get("related_results") or []), *(rec.get("results") or [])]  # the order the results page uses
    context = body.get("patient_medical_context") or {}
    last = turns[-1]
    return {"query_id": q["query_id"], "stratum": q["stratum"], "gold_specialty": q["specialty"],
            "gold_procedure": q["procedure"], "turns": turns, "follow_ups": len(turns) - 1,
            "final_specialty": last["specialty"] if last["workflow_status"] == "completed" else None,
            "final_decision": last["decision"], "workflow_status": last["workflow_status"],
            "procedures_step1": context.get("procedures") or [], "step2_status": rec.get("status"),
            "related_specialty": rec.get("related_specialty"),
            "hospital_ids": [h.get("hospital_id") for h in shown],
            "hospital_names": [h.get("hospital_name") for h in shown],
            "outside_area": [bool(h.get("outside_area")) for h in shown],
            "client_ms_total": sum(t["client_ms"] for t in turns)}


def cmd_run(args) -> None:
    import requests
    gold = ev.load_gold(args.gold)
    if args.only:
        gold = [q for q in gold if q["query_id"] in set(args.only.split(","))]
    out = RUNS / (datetime.now().strftime("%Y%m%d_%H%M%S") + "_hospitals")
    out.mkdir(parents=True, exist_ok=True)
    health = requests.get(f"{args.base}/api/health", timeout=10).json()
    (out / "meta.json").write_text(json.dumps({"started": datetime.now().isoformat(timespec="seconds"),
                                               "base": args.base, "health": health, "n": len(gold),
                                               "spacing": args.spacing, "top_k": TOP_K, "git": ev.git_info(),
                                               "gold_sha256": ev.file_sha(args.gold)}, indent=2), encoding="utf-8")
    print(f"portal: {health}; {len(gold)} queries -> {out.relative_to(PROJECT_ROOT)}", flush=True)
    with (out / "results.jsonl").open("a", encoding="utf-8") as handle:
        for i, q in enumerate(gold, 1):
            started = time.perf_counter()
            row = run_one(args.base, q, args.spacing, out)
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            ok = "OK" if row["final_specialty"] == q["specialty"] else f"gold {q['specialty']}"
            print(f"[{i}/{len(gold)}] {q['query_id']} {row['final_decision']}/{row['final_specialty']} {ok} "
                  f"follow-ups={row['follow_ups']} hospitals={len(row['hospital_ids'])} {row['client_ms_total']} ms",
                  flush=True)
            wait = args.spacing - (time.perf_counter() - started)
            if wait > 0 and i < len(gold):
                time.sleep(wait)
    print(f"done. Next: pool {out.name}, grade, score {out.name}")


def load_rows(run: Path) -> list[dict]:
    return [json.loads(line) for line in (run / "results.jsonl").read_text(encoding="utf-8").splitlines() if line]


def resolve_run(name: str) -> Path:
    path = Path(name)
    return path.resolve() if path.exists() else RUNS / name


# --------------------------------------------------------------------------- pool

def cmd_pool(args) -> None:
    """Write the (hospital, gold need) pairs the portal showed in its top 5 that have no grade yet."""
    run = resolve_run(args.run)
    systems = ev.Systems()
    gold = {q["query_id"]: q for q in ev.load_gold(args.gold)}
    grades = ev.load_grades(args.grades, systems.metadata)
    by_id = {h["hospital_id"]: h for h in systems.metadata}
    wanted: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for row in load_rows(run):
        q = gold[row["query_id"]]
        for hid in row["hospital_ids"][:SHOWN]:
            if hid not in grades.get(q["need"], {}):
                wanted[(hid, q["specialty"], q["procedure"])].add(q["query_id"])
    with ev.TO_GRADE_FILE.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(ev.GRADE_COLUMNS[:4] + ["city", "official_source_url", "queries"] + ev.GRADE_COLUMNS[4:])
        for (hid, specialty, procedure), qids in sorted(wanted.items()):
            h = by_id[hid]
            writer.writerow([hid, h["hospital_name"], specialty, procedure, h["city"], h.get("official_source_url", ""),
                             ";".join(sorted(qids))] + [""] * (len(ev.GRADE_COLUMNS) - 4))
    print(f"{len(wanted)} ungraded (hospital, need) pairs in the portal's top {SHOWN} -> "
          f"{ev.TO_GRADE_FILE.relative_to(PROJECT_ROOT)}")
    if wanted:
        print("Grade them: scripts/step2_draft_grades.py --budget 0.15, then run `score`.")


# --------------------------------------------------------------------------- score

METRICS = ["NDCG@5", "NDCG@3", "P@3", "P@5", "R@3", "R@5", "Hit@3", "Capable@3", "Bad@3", "OffArea@3", "MaxP@5"]


def cmd_score(args) -> None:
    run = resolve_run(args.run)
    rows = load_rows(run)
    systems = ev.Systems()
    gold = {q["query_id"]: q for q in ev.load_gold(args.gold)}
    grades = ev.load_grades(args.grades, systems.metadata, judged_only=args.judged_only)

    def ranked_list(ids: list[str], capability: dict) -> list[str]:
        if args.judged_only:  # condensed list, as eval_step2 --judged-only: drop hospitals without an evidence grade
            return [h for h in ids if h in capability][:SHOWN]
        return ids[:SHOWN]

    lines_out = {"portal": [], "oracle": [], "B0": []}
    values = {s: defaultdict(list) for s in lines_out}
    by_stratum = defaultdict(lambda: {s: defaultdict(list) for s in lines_out})
    split = {"Step 1 right": defaultdict(list), "Step 1 wrong / no answer": defaultdict(list)}
    unjudged, per_query = [], []
    for row in rows:
        q = gold[row["query_id"]]
        area = systems.area_ids(q)
        capability = grades.get(q["need"], {})
        rel = {hid: g for hid, g in capability.items() if hid in area}
        candidates = {
            "portal": [ranked_list(row["hospital_ids"], capability)],
            "oracle": [ranked_list(systems.ours(q, ev.CONDENSED_DEPTH if args.judged_only else SHOWN), capability)],
            "B0": [ranked_list(systems.b0(q, ev.CONDENSED_DEPTH if args.judged_only else SHOWN, seed), capability)
                   for seed in range(args.seeds)],
        }
        missing = [h for h in candidates["portal"][0] if h in area and h not in capability]
        if missing:
            unjudged.append(f"{q['query_id']}: {missing}")
        step1_ok = row["final_specialty"] == q["specialty"]
        record = {"query_id": q["query_id"], "stratum": q["stratum"], "gold_specialty": q["specialty"],
                  "portal_specialty": row["final_specialty"], "step1_ok": step1_ok, "follow_ups": row["follow_ups"],
                  "n_relevant": rm.relevant_count(rel), "portal_top5": ";".join(candidates["portal"][0])}
        for system, lists in candidates.items():
            runs = [ev.query_metrics(r, rel, capability, area) for r in lists]
            merged = {k: rm.mean([m[k] for m in runs]) for k in runs[0]}
            for k, v in merged.items():
                values[system][k].append(v)
                by_stratum[q["stratum"]][system][k].append(v)
                if system == "portal":
                    split["Step 1 right" if step1_ok else "Step 1 wrong / no answer"][k].append(v)
            record.update({f"{system}:{k}": merged[k] for k in ("NDCG@5", "P@5", "R@5")})
        per_query.append(record)

    label = {"portal": "Portal end to end (patient text → Step 1 → Step 2)",
             "oracle": "Reference: engine with the gold speciality + procedure (no Step 1)",
             "B0": f"Baseline B0: random among eligible ({args.seeds} seeds)"}
    summary = {s: {k: {"mean": rm.mean(v), "ci95": rm.bootstrap_ci(v), "n": sum(x is not None for x in v)}
                   for k, v in values[s].items()} for s in lines_out}
    p_oracle = rm.paired_permutation_p(values["portal"]["NDCG@5"], values["oracle"]["NDCG@5"])
    p_b0 = rm.paired_permutation_p(values["portal"]["NDCG@5"], values["B0"]["NDCG@5"])
    step1_right = sum(r["step1_ok"] for r in per_query)
    decisions = Counter(r["final_decision"] for r in rows)
    gave_up = [f"{r['query_id']}: {t['gave_up']}" for r in rows for t in r["turns"] if t.get("gave_up")]
    failures = [r["query_id"] for r in rows if any(t["http"] != 200 for t in r["turns"])]

    mode = "judged-only (condensed lists: hospitals without a website-backed grade dropped)" if args.judged_only \
        else "all grades (draft grades included; unjudged hospitals count as 0)"
    out_name = "metrics_judged.json" if args.judged_only else "metrics.json"
    metrics = {"run": run.name, "mode": mode, "queries": len(rows), "summary": summary,
               "by_stratum": {st: {s: {k: rm.mean(v) for k, v in m.items()} for s, m in d.items()}
                              for st, d in sorted(by_stratum.items())},
               "portal_by_step1": {k: {m: rm.mean(v) for m, v in d.items()} | {"n": len(d["NDCG@5"])}
                                   for k, d in split.items()},
               "p_ndcg5_portal_vs_oracle": p_oracle, "p_ndcg5_portal_vs_B0": p_b0,
               "step1_correct": step1_right, "decisions": dict(decisions), "gave_up": gave_up,
               "http_failures": failures, "unjudged_in_area": unjudged,
               "grades_sha256": ev.file_sha(args.grades)}
    (run / out_name).write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    with (run / ("per_query_judged.csv" if args.judged_only else "per_query.csv")).open("w", encoding="utf-8",
                                                                                        newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(per_query[0]))
        writer.writeheader()
        writer.writerows(per_query)

    def cell(stat):
        if stat["mean"] is None:
            return "–"
        ci = stat["ci95"]
        return f"{stat['mean']:.3f}" + (f" [{ci[0]:.2f}, {ci[1]:.2f}]" if ci else "")

    md = [f"# Portal hospital benchmark — {run.name}", "", f"Mode: {mode}. {len(rows)} queries "
          f"(data/evaluation/step2_gold.csv). Relevant = website grade ≥ 2 in the patient's area; NDCG gain 2^grade − 1.",
          "", f"Step 1 picked the gold speciality in {step1_right}/{len(rows)} searches "
          f"(final decisions: {', '.join(f'{k} {v}' for k, v in decisions.most_common())}).", "",
          "| System | " + " | ".join(METRICS) + " |", "|---|" + "---|" * len(METRICS)]
    for s in lines_out:
        md.append(f"| {label[s]} | " + " | ".join(cell(summary[s][k]) if k.startswith("NDCG")
                                                  else (f"{summary[s][k]['mean']:.3f}" if summary[s][k]["mean"] is not None else "–")
                                                  for k in METRICS) + " |")
    md += ["", f"Paired permutation test of NDCG@5: portal vs reference p = {p_oracle:.3f}; portal vs B0 p = {p_b0:.3f}.",
           "", "## Portal by Step 1 outcome", "", "| Step 1 | Queries | NDCG@5 | P@5 | R@5 | Hit@3 |", "|---|---|---|---|---|---|"]
    for k, d in split.items():
        md.append(f"| {k} | {len(d['NDCG@5'])} | " + " | ".join(
            f"{rm.mean(d[m]):.3f}" if rm.mean(d[m]) is not None else "–" for m in ("NDCG@5", "P@5", "R@5", "Hit@3")) + " |")
    md += ["", "## NDCG@5 by stratum", "", "| Stratum | Portal | Reference | B0 |", "|---|---|---|---|"]
    for st, d in sorted(by_stratum.items()):
        md.append(f"| {st} | " + " | ".join(f"{rm.mean(d[s]['NDCG@5']):.3f}" if rm.mean(d[s]["NDCG@5"]) is not None
                                             else "–" for s in lines_out) + " |")
    md += ["", "## Searches where Step 1 did not end on the gold speciality", "",
           "| Query | Gold | Portal | Follow-ups | Portal NDCG@5 |", "|---|---|---|---|---|"]
    for r in per_query:
        if not r["step1_ok"]:
            v = r["portal:NDCG@5"]
            md.append(f"| {r['query_id']} | {r['gold_specialty']} | {r['portal_specialty'] or '(none)'} | "
                      f"{r['follow_ups']} | {'–' if v is None else f'{v:.3f}'} |")
    md += ["", "## Notes", "",
           "- The simulated patient answers follow-up questions with the gold speciality's body area and picks the gold "
           "speciality from a shortlist only when it is offered: favourable to the portal.",
           "- Grades are LLM drafts from the hospitals' websites awaiting the 20% human check.",
           "- `–` = no relevant hospital exists for that query, so P/R/NDCG are undefined and left out of the mean.",
           f"- Gave up: {'; '.join(gave_up) or 'none'}. HTTP failures: {', '.join(failures) or 'none'}.",
           f"- Unjudged hospitals in the area in the portal's top {SHOWN}: {'; '.join(unjudged) or 'none'}."]
    report = "\n".join(md) + "\n"
    (run / ("report_judged.md" if args.judged_only else "report.md")).write_text(report, encoding="utf-8")
    print(report)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gold", type=Path, default=ev.GOLD_FILE)
    parser.add_argument("--grades", type=Path, default=ev.GRADES_FILE)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run")
    p_run.add_argument("--base", default="http://127.0.0.1:8000")
    p_run.add_argument("--spacing", type=float, default=12.0, help="seconds between portal requests")
    p_run.add_argument("--only", default="", help="comma-separated query ids (test)")
    p_pool = sub.add_parser("pool")
    p_pool.add_argument("run")
    p_score = sub.add_parser("score")
    p_score.add_argument("run")
    p_score.add_argument("--judged-only", action="store_true")
    p_score.add_argument("--seeds", type=int, default=20)
    args = parser.parse_args()
    {"run": cmd_run, "pool": cmd_pool, "score": cmd_score}[args.cmd](args)


if __name__ == "__main__":
    main()
