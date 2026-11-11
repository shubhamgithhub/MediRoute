"""Exercise Step 1 through the running API (POST /api/analyze) and print one line per call.

Start the API first (python -m uvicorn mediroute.backend.main:app --port 8000), then:

    python scripts/api_smoke_step1.py                 # all scenarios
    python scripts/api_smoke_step1.py --base http://127.0.0.1:8000

Each line shows the request_id, so the full trace can be found in logs/step1_trace.jsonl.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8000"


def analyze(base: str, **body) -> dict:
    payload = {"requirement": "", "location": "Chennai", "language": "English", "debug": True, **body}
    request = urllib.request.Request(f"{base}/api/analyze", data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
    start = time.perf_counter()
    with urllib.request.urlopen(request, timeout=300) as response:
        result = json.loads(response.read().decode("utf-8"))["medicalContext"]
    result["_client_ms"] = int((time.perf_counter() - start) * 1000)
    return result


def show(label: str, r: dict) -> None:
    votes = {k: (v["top3"][0][0] if v["top3"] else "-") for k, v in (r.get("debug") or {}).get("votes", {}).items()}
    print(f"{label:<34} {r['decision']:<23} {str(r['suggested_specialty']):<24} "
          f"emergency={str(r['emergency']):<5} votes={votes} evidence={r['evidence'][:3]} "
          f"{r['_client_ms']} ms  rid={r['request_id']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=BASE)
    base = parser.parse_args().base

    show("1 clear diagnosis", analyze(base, requirement=(
        "My mother, 62, has severe osteoarthritis of both knees. Her surgeon recommended knee replacement.")))
    show("2 procedure only", analyze(base, requirement="Doctor advised CABG for my father."))
    show("3 report text", analyze(base, requirement="Please see my father's angiography report.", reportText=(
        "CORONARY ANGIOGRAPHY\nLAD: 90% proximal stenosis. LCx: 80%. RCA: 70%.\n"
        "IMPRESSION: Triple vessel disease.\nADVICE: CABG.")))
    show("4 emergency", analyze(base, requirement="My father suddenly has crushing chest pain, is sweating and cannot breathe."))
    show("5 phone number is redacted", analyze(base, requirement="Cataract in both eyes, call me on +91 98765 43210"))

    # 6 vague text -> clarification form -> answers -> result
    first = analyze(base, requirement="weakness")
    show("6a vague, round 0", first)
    second = analyze(base, requirement="weakness", clarificationRound=1, parentRequestId=first["request_id"],
                     clarification={"body_area": "Bones, joints and muscles",
                                    "existing_diagnosis": "slipped disc L4-L5", "recommended_procedure": ""})
    show("6b after answering the form", second)

    # 7 still unclear after two forms -> the user picks from the list
    r1 = analyze(base, requirement="I need surgery in India")
    show("7a vague, round 0", r1)
    r2 = analyze(base, requirement="I need surgery in India", clarificationRound=1, parentRequestId=r1["request_id"],
                 clarification={"body_area": "Other / not sure"})
    show("7b round 1, no detail", r2)
    r3 = analyze(base, requirement="I need surgery in India", clarificationRound=2, parentRequestId=r1["request_id"],
                 clarification={"body_area": "Other / not sure"})
    show("7c round 2 -> user choice", r3)
    if r3.get("user_choice"):
        print(f"{'':<34} options offered first: {r3['user_choice']['suggested_first'][:5]}")
    r4 = analyze(base, requirement="I need surgery in India", clarificationRound=2, parentRequestId=r1["request_id"],
                 selectedSpecialty="Orthopaedics")
    show("7d user picked Orthopaedics", r4)


if __name__ == "__main__":
    main()
