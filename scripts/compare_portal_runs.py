"""Before / after table for two portal runs of the same requests (scripts/portal_benchmark.py).

    PYTHONPATH=src python scripts/compare_portal_runs.py data/evaluation/portal_runs/<before> data/evaluation/portal_runs/<after>

Scores each run per gold set on
  first answer   correct / confidently wrong / asks (they add up to the set's requests)
  after 1 answer the simulated patient answered the body-area question once (runs made with
                 --answer-once); a run without it keeps its asks as "still open"
against two label sets: the current gold labels, and for gretel the draft rule labels in
data/evaluation/step1_gold_gretel_rule_review.csv (not yet doctor-reviewed).
Writes <after>/comparison.md and prints it.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import benchmark_step1 as bench  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "data" / "evaluation" / "step1_gold_gretel_rule_review.csv"
SETS = ("core50", "mediroute", "gretel")


def labels(kind: str) -> dict:
    gold = {(s, g["query_id"]): {g["expected_specialty"], *g["alternatives"]} for s in SETS for g in bench.load_gold(s)}
    if kind == "rule":
        for r in csv.DictReader(RULES.open(encoding="utf-8-sig")):
            gold[("gretel", r["query_id"])] = {r["rule_expected"], *[a for a in r["rule_alternatives"].split(";") if a]}
    return gold


def score(run: Path, ok: dict, kind: str = "current") -> dict:
    rows = [json.loads(l) for l in (run / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    out = {s: {"n": 0, "correct": 0, "wrong": 0, "asks": 0, "after_correct": 0, "after_wrong": 0, "after_open": 0,
               "emergency": 0} for s in SETS + ("all",)}
    for r in rows:
        good = ok[(r["gold_set"], r["query_id"])]
        first = r["specialty"]
        second = r.get("specialty2_rule", r.get("specialty2")) if kind == "rule" else r.get("specialty2")
        final = second if first is None and "decision2" in r else first
        for key in (r["gold_set"], "all"):
            c = out[key]
            c["n"] += 1
            c["asks" if first is None else ("correct" if first in good else "wrong")] += 1
            c["after_open" if final is None else ("after_correct" if final in good else "after_wrong")] += 1
            c["emergency"] += r.get("decision") == "emergency_rule"
    return out


def pct(c: dict, k: str) -> str:
    return f"{c[k] / c['n']:.0%} ({c[k]})" if c["n"] else "–"


def main() -> None:
    before, after = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    lines = [f"# Portal runs compared: {before.name} → {after.name}", "",
             "First answer: correct + confidently wrong + asks = 100% per row. After 1 answer: the simulated patient "
             "answered the body-area question once (favourable by construction: the answer comes from the expected "
             "speciality). Rule labels: draft, not yet doctor-reviewed (gretel only; core50 and mediroute unchanged).", ""]
    for kind, title in (("current", "Current gold labels"), ("rule", "Gretel rule labels (draft)")):
        ok = labels(kind)
        b, a = score(before, ok, kind), score(after, ok, kind)
        lines += [f"## {title}", "",
                  "| Set | Run | Correct | Confidently wrong | Asks | After 1 answer: correct | still wrong | still open |",
                  "|---|---|---|---|---|---|---|---|"]
        for s in SETS + ("all",):
            for name, c in (("before", b[s]), ("after", a[s])):
                lines.append(f"| {s} (n={c['n']}) | {name} | {pct(c, 'correct')} | {pct(c, 'wrong')} | {pct(c, 'asks')} | "
                             f"{pct(c, 'after_correct')} | {pct(c, 'after_wrong')} | {pct(c, 'after_open')} |")
        lines.append("")
    report = "\n".join(lines)
    (after / "comparison.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
