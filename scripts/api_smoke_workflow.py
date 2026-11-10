"""Exercise the integrated workflow (POST /api/patient-routing: reports + text -> Step 1 -> Step 2).

Start the API first, wait for "Step 1 LLM warm-up done" in logs/mediroute.log, then:

    python scripts/api_smoke_workflow.py

Uses the synthetic test reports in data/raw/test_reports (from Shubham's Step 12 work). Each line
shows the workflow_id and the Step 1 request_id, so the full trace can be found in
logs/step1_trace.jsonl.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import requests

BASE = "http://127.0.0.1:8000"
REPORTS = Path(__file__).resolve().parents[1] / "data" / "raw" / "test_reports"


def route(base: str, requirement: str = "", pdfs: tuple[str, ...] = (), city: str | None = None,
          state: str | None = None, **extra) -> dict:
    data = {"requirement": requirement, "top_k": "5", **{k: str(v) for k, v in extra.items()}}
    if city:
        data["preferred_city"] = city
    if state:
        data["preferred_state"] = state
    files = [("files", (name, (REPORTS / name).read_bytes(), "application/pdf")) for name in pdfs]
    start = time.perf_counter()
    response = requests.post(f"{base}/api/patient-routing", data=data, files=files or None, timeout=600)
    result = response.json()
    result["_http"] = response.status_code
    result["_ms"] = int((time.perf_counter() - start) * 1000)
    return result


def show(label: str, r: dict) -> None:
    step1 = r.get("step1") or {}
    rec = r.get("recommendation_result") or {}
    top = [h.get("hospital_name") for h in (rec.get("results") or [])[:3]]
    print(f"{label:<40} HTTP {r['_http']} {r.get('workflow_status', '-'):<26} "
          f"step1={step1.get('decision', '-')}/{step1.get('suggested_specialty')}  "
          f"step2={rec.get('status', '-')}({rec.get('count', 0)}) {top}  "
          f"{r['_ms']} ms  wf={r.get('workflow_id')} s1={step1.get('request_id')}")
    if r.get("clarification_required"):
        print(f"{'':<40} clarification ({r.get('clarification_type')}): {r.get('clarification_reason')}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=BASE)
    base = parser.parse_args().base

    show("1 text only (CABG), Chennai", route(base, "Doctor advised CABG for my father.", city="Chennai", state="Tamil Nadu"))
    show("2 text only (knee), no city", route(base, "My mother has severe osteoarthritis of both knees; surgeon advised knee replacement."))
    show("3 PDF only (coronary artery disease)", route(base, pdfs=("MediRoute_Report_01_Coronary_Artery_Disease.pdf",)))
    show("4 PDF + text (atrial fibrillation ECG)", route(base, "Please see my ECG report.", pdfs=("11_abnormal_MR-SYN-203.pdf",)))
    show("5 PDF only (type 2 diabetes)", route(base, pdfs=("MediRoute_Report_03_Type_2_Diabetes.pdf",)))

    first = route(base, "weakness")
    show("6a vague text -> Step 1 question", first)
    rid = (first.get("step1") or {}).get("request_id")
    second = route(base, "weakness", clarification_round=1, parent_request_id=rid,
                   clarification_body_area="Bones, joints and muscles",
                   clarification_existing_diagnosis="slipped disc L4-L5")
    show("6b answers -> hospitals", second)

    show("7 speciality with no hospital (cataract)", route(base, "Cataract surgery for both eyes."))
    show("8 city with no match (CABG, Kochi)", route(base, "CABG surgery", city="Kochi", state="Kerala"))
    show("9 blank PDF, no text", route(base, pdfs=("MediRoute_Blank_Test.pdf",)))


if __name__ == "__main__":
    main()
