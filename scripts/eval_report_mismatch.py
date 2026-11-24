"""Typed text vs attached report (Step 1, in process, real LLM and lookup).

Cases: data/evaluation/step1_report_mismatch_set.csv (mismatch: the text decides and a notice is
shown; agrees: the report is used, no notice) plus every core50 case with a report (no notice
expected: their text is vague or says the same thing, e.g. "Thyroid report attached").

    PYTHONPATH=src .venv/Scripts/python.exe scripts/eval_report_mismatch.py --spacing 4

Writes data/evaluation/results/<timestamp>_report_mismatch/results.csv and summary.md.
"""

from __future__ import annotations

import argparse
import csv
import time
from datetime import datetime

from dotenv import load_dotenv

from mediroute.utils.paths import EVALUATION_DIR

SET_FILE = EVALUATION_DIR / "step1_report_mismatch_set.csv"
GOLD_FILE = EVALUATION_DIR / "step1_gold_core50.csv"


def load_cases() -> list[dict]:
    with open(SET_FILE, encoding="utf-8-sig", newline="") as handle:
        cases = list(csv.DictReader(handle))
    with open(GOLD_FILE, encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["report_text"].strip():
                cases.append({"case_id": row["query_id"], "group": "core50 report", "text": row["query"],
                              "report_text": row["report_text"],
                              "expected": ";".join(x for x in [row["expected_specialty"],
                                                               *row["acceptable_alternatives"].split(";")] if x),
                              "notice": "no", "note": row["case_type"]})
    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--spacing", type=float, default=4.0, help="seconds between cases (provider rate limit)")
    args = parser.parse_args()
    load_dotenv()
    from mediroute.specialty_routing.step1.pipeline import Step1Input, Step1Pipeline

    pipe = Step1Pipeline()
    out_dir = EVALUATION_DIR / "results" / f"{datetime.now():%Y%m%d_%H%M%S}_report_mismatch"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, case in enumerate(load_cases()):
        if i:
            time.sleep(args.spacing)
        out = pipe.analyze(Step1Input(text=case["text"], report_text=case["report_text"]))
        got = out.get("suggested_specialty") or ""
        expected = case["expected"].split(";")
        notice = bool(out.get("report_notice"))
        notice_ok = notice == (case["notice"] == "yes")
        # a question is not confidently wrong; only a wrong speciality counts as wrong
        specialty_ok = got in expected if got else None
        rows.append({"case_id": case["case_id"], "group": case["group"], "expected": case["expected"],
                     "got": got or "ask", "decision": out.get("decision"), "notice_expected": case["notice"],
                     "notice_shown": notice, "notice_ok": notice_ok,
                     "specialty": "correct" if specialty_ok else "ask" if specialty_ok is None else "WRONG",
                     "request_id": out.get("request_id")})
        print(f"{case['case_id']:<5} {case['group']:<13} notice {'ok ' if notice_ok else 'BAD'} "
              f"{rows[-1]['specialty']:<8} {got or 'ask':<24} expected {case['expected']}")

    with open(out_dir / "results.csv", "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    lines = [f"# Report vs typed text: {out_dir.name}", "",
             "| Group | Cases | Notice as expected | Correct | Ask | Wrong |", "|---|---|---|---|---|---|"]
    for group in dict.fromkeys(r["group"] for r in rows):
        g = [r for r in rows if r["group"] == group]
        lines.append(f"| {group} | {len(g)} | {sum(r['notice_ok'] for r in g)} | "
                     f"{sum(r['specialty'] == 'correct' for r in g)} | {sum(r['specialty'] == 'ask' for r in g)} | "
                     f"{sum(r['specialty'] == 'WRONG' for r in g)} |")
    bad = [r for r in rows if not r["notice_ok"] or r["specialty"] == "WRONG"]
    if bad:
        lines += ["", "Not as expected:", ""] + [f"- {r['case_id']}: got {r['got']} (notice {r['notice_shown']}), "
                                                  f"expected {r['expected']} (notice {r['notice_expected']})" for r in bad]
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
