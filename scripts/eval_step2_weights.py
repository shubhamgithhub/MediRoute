"""Ranking-weight sensitivity for Step 2: does the ranking depend on the exact bonus weights?

    PYTHONPATH=src python scripts/eval_step2_weights.py            # judged-only, as the reported Step 2 run
    PYTHONPATH=src python scripts/eval_step2_weights.py --all-grades

The TA asked for alternative ranking weights to be tested rather than chosen by hand. This reruns the
real engine ("ours" in eval_step2.py) on the Step 2 gold set once per weight variant, changing only
the reranker's WEIGHTS table (hospital_reranker.py), and scores every variant with the same metrics
and grades as eval_step2.py. No LLM, no API cost; the app code is not changed.

Variants
    current            the weights the app uses
    no bonuses         similarity only (every bonus 0)
    all x0.5 / x2 / x4 every bonus and the cap scaled
    without <bonus>    one bonus set to 0 at a time (leave-one-out)
    no area filter     current weights, searched across India (tests "suitability before location":
                       read Capable@3 and OffArea@3; NDCG counts only in-area hospitals, so it drops by design)

Output: data/evaluation/results/<run>_step2_weights/ report.md, metrics.json, per_query.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import eval_step2 as E  # noqa: E402
from mediroute.evaluation import ranking_metrics as rm  # noqa: E402
from mediroute.hospital_recommendation.ranking import hospital_reranker as R  # noqa: E402

BONUS_GROUPS = {  # leave-one-out groups: keys of WEIGHTS that belong to one bonus
    "website-confirmed speciality": ["website_specialty"],
    "procedure match": ["procedure_each", "procedure_max"],
    "verified details": ["verified", "partially_verified"],
    "NABH": ["nabh"],
    "JCI": ["jci"],
    "international services": ["international_patients"],
    "evidence quality": ["evidence_max"],
}
SHOWN = ["NDCG@5", "NDCG@3", "P@3", "Hit@3", "Capable@3", "Bad@3", "OffArea@3"]


def variants(base: dict) -> list[tuple[str, dict, bool]]:
    """(label, weights, search all of India)"""
    out = [("current", dict(base), False),
           ("no bonuses (similarity only)", {k: 0.0 for k in base}, False)]
    for f in (0.5, 2, 4):
        out.append((f"all bonuses x{f}", {k: v * f for k, v in base.items()}, False))
    for label, keys in BONUS_GROUPS.items():
        w = dict(base)
        for k in keys:
            w[k] = 0.0
        out.append((f"without {label}", w, False))
    out.append(("no area filter (all India)", dict(base), True))
    return out


def run_variant(systems, gold, grades, weights, all_india, judged_only):
    R.WEIGHTS.clear()
    R.WEIGHTS.update(weights)
    values, rows = defaultdict(list), []
    for q in gold:
        area = systems.area_ids(q)
        capability = grades.get(q["need"], {})
        rel = {h: g for h, g in capability.items() if h in area}
        qq = dict(q, preferred_city="", preferred_state="") if all_india else q
        depth = E.CONDENSED_DEPTH if judged_only else max(E.KS)
        ranked = systems.ours(qq, depth)
        if judged_only:
            ranked = [h for h in ranked if h in capability][:max(E.KS)]
        m = E.query_metrics(ranked[:max(E.KS)], rel, capability, area)
        rows.append({"query_id": q["query_id"], "stratum": q["stratum"], **m, "top5": ";".join(ranked[:5])})
        for k, v in m.items():
            values[k].append(v)
    return values, rows


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all-grades", action="store_true", help="also use low-confidence fallback grades")
    args = ap.parse_args(argv)
    judged_only = not args.all_grades

    gold = E.load_gold(E.GOLD_FILE)
    systems = E.Systems()
    grades = E.load_grades(E.GRADES_FILE, systems.metadata, judged_only=judged_only)
    base = dict(R.WEIGHTS)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_step2_weights" + ("" if judged_only else "_allgrades")
    out_dir = E.RESULTS_DIR / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    results, per_query = {}, []
    try:
        for label, weights, all_india in variants(base):
            values, rows = run_variant(systems, gold, grades, weights, all_india, judged_only)
            results[label] = {"weights": weights, "all_india": all_india, "values": values,
                              "top5": [r["top5"] for r in rows]}
            per_query += [{"variant": label, **r} for r in rows]
            print(f"{label:38s} NDCG@5 {rm.mean(values['NDCG@5']):.3f}  Capable@3 {rm.mean(values['Capable@3']):.3f}")
    finally:
        R.WEIGHTS.clear()
        R.WEIGHTS.update(base)

    cur = results["current"]
    summary = {}
    for label, r in results.items():
        v = r["values"]
        changed = sum(a != b for a, b in zip(r["top5"], cur["top5"]))
        changed_top1 = sum(a.split(";")[0] != b.split(";")[0] for a, b in zip(r["top5"], cur["top5"]))
        summary[label] = {
            "metrics": {k: {"mean": rm.mean(v[k]), "ci95": rm.bootstrap_ci(v[k]) if k.startswith("NDCG") else None}
                        for k in SHOWN},
            "p_vs_current_ndcg5": None if label == "current" else rm.paired_permutation_p(cur["values"]["NDCG@5"], v["NDCG@5"]),
            "queries_top5_changed": changed, "queries_top1_changed": changed_top1,
            "weights": r["weights"], "all_india": r["all_india"]}

    metrics = {"run_id": run_id, "mode": "oracle · " + ("judged-only (condensed lists)" if judged_only else "all grades"),
               "queries": len(gold), "git": E.git_info(), "base_weights": base, "variants": summary,
               "data_sha256": {"hospitals.csv": E.file_sha(E.HOSPITALS_FILE), "grades": E.file_sha(E.GRADES_FILE),
                               "gold": E.file_sha(E.GOLD_FILE)}}
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    with (out_dir / "per_query.csv").open("w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=list(per_query[0]))
        w.writeheader()
        w.writerows(per_query)
    report = render(metrics)
    (out_dir / "report.md").write_text(report, encoding="utf-8")
    print("\n" + report + f"\nWritten to {out_dir.relative_to(E.PROJECT_ROOT)}")


def render(m: dict) -> str:
    lines = [f"# Step 2 ranking-weight sensitivity {m['run_id']}", "",
             f"Mode: {m['mode']} · queries: {m['queries']} · git {m['git']['commit']}{' (dirty)' if m['git']['dirty'] else ''}"
             f" · grades {m['data_sha256']['grades']}", "",
             "Only the reranker's bonus weights change; retrieval, filters and grades are the same as eval_step2.py. "
             "p = paired permutation test of NDCG@5 against the current weights. "
             "“Top-5 changed” = queries whose top 5 differs from the current weights.", "",
             "Current weights: " + ", ".join(f"{k} {v}" for k, v in m["base_weights"].items()), "",
             "| Variant | " + " | ".join(SHOWN) + " | p (NDCG@5) | Top-5 changed | Top-1 changed |",
             "|---|" + "---|" * (len(SHOWN) + 3)]
    for label, s in m["variants"].items():
        cells = []
        for k in SHOWN:
            x = s["metrics"][k]
            text = "–" if x["mean"] is None else f"{x['mean']:.3f}"
            if x["ci95"] and x["mean"] is not None:
                text += f" [{x['ci95'][0]:.2f}, {x['ci95'][1]:.2f}]"
            cells.append(text)
        p = s["p_vs_current_ndcg5"]
        lines.append(f"| {label} | " + " | ".join(cells) + f" | {'–' if p is None else f'{p:.3f}'} | "
                     f"{s['queries_top5_changed']} | {s['queries_top1_changed']} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
