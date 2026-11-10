"""Evaluate Step 1 routes (rules, LLM, hybrid) on gold query sets.

Usage:
    python scripts/eval_step1.py                       # rules + llm + hybrid on both gold sets
    python scripts/eval_step1.py --routes rules        # rules only (seconds, no Ollama needed)
    python scripts/eval_step1.py --model qwen2.5:3b    # compare another local model

Writes, per run, to data/evaluation/results/<run_id>/:
    predictions.csv  one row per query x route
    metrics.json     metrics per gold set x route
    report.md        the same as readable tables
Hybrid needs no extra LLM calls: it combines the rules and LLM predictions.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from mediroute.common.specialties import specialty_names
from mediroute.specialty_routing.routes import (
    DEFAULT_MODEL,
    DEFAULT_PROMPT_VERSION,
    UNCLEAR,
    LLMRouter,
    RuleRouter,
    combine,
)
from mediroute.utils.paths import DATA_DIR

GOLD_DIR = DATA_DIR / "evaluation"
DEFAULT_GOLD = ["step1_gold_mediroute.csv", "step1_gold_gretel.csv"]


def load_gold(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    names = set(specialty_names())
    for row in rows:
        row["alternatives"] = [a.strip() for a in row["acceptable_alternatives"].split(";") if a.strip()]
        unknown = {row["expected_specialty"], *row["alternatives"]} - names
        if unknown:
            raise ValueError(f"{path.name} {row['query_id']}: unknown specialty {unknown}")
    return rows


def macro_f1(pairs: list[tuple[str, str]]) -> float:
    """Macro-F1 over expected classes; a prediction of Unclear counts as wrong."""
    labels = sorted({e for e, _ in pairs})
    f1s = []
    for label in labels:
        tp = sum(1 for e, p in pairs if e == label and p == label)
        fp = sum(1 for e, p in pairs if e != label and p == label)
        fn = sum(1 for e, p in pairs if e == label and p != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    return statistics.mean(f1s) if f1s else 0.0


def percentile(values: list[int], q: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]


def score(rows: list[dict]) -> dict:
    n = len(rows)
    top1 = sum(r["top1_correct"] for r in rows)
    lenient = sum(r["acceptable"] for r in rows)
    top3 = sum(r["top3_correct"] for r in rows)
    unclear = sum(r["predicted"] == UNCLEAR for r in rows)
    failed = sum(not r["ok"] for r in rows)
    latencies = [r["latency_ms"] for r in rows]
    by_conf = defaultdict(list)
    for r in rows:
        if r.get("confidence"):
            by_conf[r["confidence"]].append(r["top1_correct"])
    errors = Counter((r["expected"], r["predicted"]) for r in rows if not r["acceptable"])
    by_type = defaultdict(list)
    for r in rows:
        by_type[r["case_type"].removeprefix("gretel:")].append(r["top1_correct"])
    return {
        "n": n,
        "top1_accuracy": round(top1 / n, 3),
        "acceptable_accuracy": round(lenient / n, 3),
        "top3_accuracy": round(top3 / n, 3),
        "macro_f1": round(macro_f1([(r["expected"], r["predicted"]) for r in rows]), 3),
        "unclear_rate": round(unclear / n, 3),
        "failed_calls": failed,
        "latency_p50_ms": percentile(latencies, 0.5),
        "latency_p95_ms": percentile(latencies, 0.95),
        "by_confidence": {k: {"n": len(v), "top1_accuracy": round(sum(v) / len(v), 3)}
                          for k, v in sorted(by_conf.items())},
        "by_case_type": {k: {"n": len(v), "top1_accuracy": round(sum(v) / len(v), 3)}
                         for k, v in sorted(by_type.items())},
        "top_errors": [{"expected": e, "predicted": p, "count": c} for (e, p), c in errors.most_common(8)],
    }


def to_row(gold: dict, gold_set: str, route: str, result, confidence: str = "") -> dict:
    expected = gold["expected_specialty"]
    acceptable = {expected, *gold["alternatives"]}
    return {
        "gold_set": gold_set,
        "query_id": gold["query_id"],
        "case_type": gold["case_type"],
        "route": route,
        "query": gold["query"],
        "expected": expected,
        "alternatives": ";".join(gold["alternatives"]),
        "predicted": result.primary,
        "ranked": ";".join(result.ranked),
        "confidence": confidence,
        "top1_correct": int(result.primary == expected),
        "acceptable": int(result.primary in acceptable),
        "top3_correct": int(expected in result.ranked[:3]),
        "ok": int(result.ok),
        "latency_ms": result.latency_ms,
        "evidence_terms": ";".join(result.evidence_terms),
        "reason": result.reason,
    }


def write_report(path: Path, meta: dict, metrics: dict) -> None:
    lines = [f"# Step 1 evaluation: {meta['run_id']}", "",
             f"Model `{meta['model']}` · prompt `{meta['prompt_version']}` · routes {', '.join(meta['routes'])}", ""]
    for gold_set, by_route in metrics.items():
        lines += [f"## {gold_set}", "",
                  "| Route | n | Top-1 | Acceptable | Top-3 | Macro-F1 | Unclear | Failed | p50 ms | p95 ms |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for route, m in by_route.items():
            lines.append(f"| {route} | {m['n']} | {m['top1_accuracy']:.1%} | {m['acceptable_accuracy']:.1%} | "
                         f"{m['top3_accuracy']:.1%} | {m['macro_f1']:.3f} | {m['unclear_rate']:.1%} | "
                         f"{m['failed_calls']} | {m['latency_p50_ms']} | {m['latency_p95_ms']} |")
        if "hybrid" in by_route:
            lines += ["", "Hybrid top-1 accuracy by confidence:", ""]
            for conf, v in by_route["hybrid"]["by_confidence"].items():
                lines.append(f"- {conf}: {v['top1_accuracy']:.1%} of {v['n']}")
        lines += ["", "Top-1 accuracy by case type:", "",
                  "| Case type | " + " | ".join(by_route) + " |",
                  "|---|" + "---|" * len(by_route)]
        case_types = sorted({c for m in by_route.values() for c in m["by_case_type"]})
        for case in case_types:
            cells = [f"{by_route[r]['by_case_type'].get(case, {}).get('top1_accuracy', 0):.0%}" for r in by_route]
            n = next(iter(by_route.values()))["by_case_type"].get(case, {}).get("n", 0)
            lines.append(f"| {case} (n={n}) | " + " | ".join(cells) + " |")
        for route, m in by_route.items():
            lines += ["", f"Most common errors, {route}:", ""]
            lines += [f"- {e['expected']} → {e['predicted']} ({e['count']})" for e in m["top_errors"]] or ["- none"]
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--routes", nargs="+", default=["rules", "llm", "hybrid"],
                        choices=["rules", "llm", "hybrid"])
    parser.add_argument("--gold", nargs="+", default=DEFAULT_GOLD)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--prompt-version", default=DEFAULT_PROMPT_VERSION)
    parser.add_argument("--limit", type=int, default=0, help="first N queries per set (smoke test)")
    args = parser.parse_args()

    routes = set(args.routes)
    if "hybrid" in routes:
        routes |= {"rules", "llm"}
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + (f"_{args.model.replace(':', '-')}" if "llm" in routes else "_rules")
    out_dir = GOLD_DIR / "results" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    rules = RuleRouter()
    llm = None
    if "llm" in routes:
        llm = LLMRouter(model=args.model, prompt_version=args.prompt_version)
        llm.warm_up()

    all_rows, metrics = [], {}
    for gold_name in args.gold:
        gold_rows = load_gold(GOLD_DIR / gold_name)
        if args.limit:
            gold_rows = gold_rows[: args.limit]
        set_name = Path(gold_name).stem
        per_route = defaultdict(list)
        for index, gold in enumerate(gold_rows, start=1):
            rule_result = rules.route(gold["query"])
            if "rules" in args.routes:
                per_route["rules"].append(to_row(gold, set_name, "rules", rule_result))
            if llm:
                llm_result = llm.route(gold["query"])
                if "llm" in args.routes:
                    per_route["llm"].append(to_row(gold, set_name, "llm", llm_result))
                if "hybrid" in args.routes:
                    hybrid_result, confidence = combine(llm_result, rule_result)
                    hybrid_result.latency_ms = llm_result.latency_ms + rule_result.latency_ms
                    per_route["hybrid"].append(to_row(gold, set_name, "hybrid", hybrid_result, confidence))
                print(f"[{set_name}] {index}/{len(gold_rows)} {gold['query_id']} "
                      f"expected={gold['expected_specialty']} llm={llm_result.primary} "
                      f"rules={rule_result.primary} {llm_result.latency_ms}ms", flush=True)
        metrics[set_name] = {route: score(rows) for route, rows in per_route.items()}
        for rows in per_route.values():
            all_rows.extend(rows)

    with (out_dir / "predictions.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(all_rows[0]))
        writer.writeheader()
        writer.writerows(all_rows)
    meta = {"run_id": run_id, "model": args.model if llm else None,
            "prompt_version": args.prompt_version, "routes": args.routes, "gold": args.gold}
    (out_dir / "metrics.json").write_text(json.dumps({"meta": meta, "metrics": metrics}, indent=2), encoding="utf-8")
    write_report(out_dir / "report.md", meta, metrics)
    print((out_dir / "report.md").read_text(encoding="utf-8"))
    print(f"Results in {out_dir}")


if __name__ == "__main__":
    main()
