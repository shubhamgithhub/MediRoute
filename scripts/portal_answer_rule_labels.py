"""Second round of a portal run (--answer-once) answered from the gretel RULE labels.

    PYTHONPATH=src python scripts/portal_answer_rule_labels.py data/evaluation/portal_runs/<run>

portal_benchmark.py --answer-once lets the simulated patient answer from the current gold label.
To score fairly against the draft rule labels (data/evaluation/step1_gold_gretel_rule_review.csv),
the patient must answer from the rule label instead. For every gretel request that was asked, this
re-sends the second round with the rule-label answer when it differs from the first one, and stores
answer_rule / specialty2_rule in results.jsonl (the same answer is reused otherwise).
"""
from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import benchmark_step1 as bench  # noqa: E402
import portal_benchmark as portal  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "data" / "evaluation" / "step1_gold_gretel_rule_review.csv"


def main() -> None:
    out = Path(sys.argv[1]).resolve()
    base, spacing = "http://127.0.0.1:8000", 15.0
    rule = {r["query_id"]: r["rule_expected"] for r in csv.DictReader(RULES.open(encoding="utf-8-sig"))}
    gold = {g["query_id"]: g for g in bench.load_gold("gretel")}
    rows = [json.loads(l) for l in (out / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    todo = [r for r in rows if r["gold_set"] == "gretel" and r.get("decision2") is not None and r["query_id"] in rule]
    sent = 0
    for r in todo:
        answer = portal.simulated_answer({"expected_specialty": rule[r["query_id"]]})
        r["answer_rule"] = answer
        if answer == r.get("answer"):
            r["specialty2_rule"] = r.get("specialty2")
            continue
        started = time.perf_counter()
        body, status, _ = portal.post(base, {"requirement": gold[r["query_id"]]["query"], "top_k": "5",
                                             "clarification_body_area": answer, "clarification_round": "1",
                                             "parent_request_id": r["step1_request_id"]})
        s2 = body.get("step1") or {}
        r.update(specialty2_rule=s2.get("suggested_specialty"), decision2_rule=s2.get("decision"),
                 step1_request_id2_rule=s2.get("request_id"), http2_rule=status)
        portal.copy_trace(s2.get("request_id"), out)
        sent += 1
        print(f"{r['query_id']}: answer {answer!r} -> {r['specialty2_rule']} (rule label {rule[r['query_id']]})", flush=True)
        time.sleep(max(0.0, spacing - (time.perf_counter() - started)))
    (out / "results.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(f"{len(todo)} asked gretel requests; {sent} re-sent with the rule-label answer")


if __name__ == "__main__":
    main()
