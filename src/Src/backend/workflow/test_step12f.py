
import sys
from pathlib import Path

from src.Src.backend.workflow.patient_routing_graph import (
    PatientRoutingGraph,
)


def run_case(graph, label, pdf_paths):
    state = {
        "report_files": [
            {
                "filename": path.name,
                "content": path.read_bytes(),
            }
            for path in pdf_paths
        ],
        "patient_request": {
            "requirement": "Medical treatment",
        },
        "preferred_city": None,
        "preferred_state": None,
        "workflow_status": "started",
        "current_step": "start",
        "clarification_required": False,
        "routing_ready": False,
    }

    result = graph.invoke(state)

    validation = result.get("consistency_validation") or {}
    medical = result.get("patient_medical_context") or {}
    recommendation = result.get("recommendation_result") or {}
    documents = result.get("document_contexts") or []

    print(f"\n{label}")
    print("-" * 55)
    print("Workflow:", result.get("workflow_status"))
    print("Routing ready:", result.get("routing_ready"))
    print("Diagnoses:", medical.get("diagnoses"))
    print("Specialties:", medical.get("canonical_specialties"))
    print("Validation:", validation.get("status"))
    print("Document contexts:", len(documents))
    print("Recommendations:", recommendation.get("count", 0))
    print("Clarification:", result.get("clarification_reason"))
    print("Error:", result.get("error_message"))

    return result


def main():
    if len(sys.argv) != 4:
        print(
            "Usage: python -m "
            "src.Src.backend.workflow.test_step12f "
            "<cardiac_pdf> <heart_failure_pdf> <diabetes_pdf>"
        )
        sys.exit(2)

    cardiac, heart_failure, diabetes = [
        Path(value) for value in sys.argv[1:]
    ]

    for path in (cardiac, heart_failure, diabetes):
        if not path.is_file():
            print(f"PDF not found: {path}")
            sys.exit(2)

    graph = PatientRoutingGraph()

    # T001: A single routable specialty
    one = run_case(
        graph, "T001 - Single cardiac PDF", [cardiac]
    )

    # T002: Two reports with the same specialty
    same = run_case(
        graph,
        "T002 - Two Cardiology PDFs",
        [cardiac, heart_failure],
    )

    # T003: Two different specialties
    conflict = run_case(
        graph,
        "T003 - Cardiology + Endocrinology",
        [cardiac, diabetes],
    )

    checks = [
        (
            "T001 single cardiac report",
            one.get("workflow_status") == "completed"
            and one.get("routing_ready") is True,
        ),
        (
            "T002 consistent multi-report routing",
            same.get("workflow_status") == "completed"
            and same.get("routing_ready") is True
            and len(same.get("document_contexts") or []) == 2,
        ),
        (
            "T003 conflict clarification",
            conflict.get("workflow_status")
            == "waiting_for_clarification"
            and conflict.get("routing_ready") is False,
        ),
    ]

    print("\nSTEP 12F TEST SUMMARY")
    print("=" * 55)

    for name, passed in checks:
        print(f"{'PASS' if passed else 'FAIL'} - {name}")

    passed = sum(ok for _, ok in checks)
    print(f"\nPassed: {passed}/{len(checks)}")

    if passed != len(checks):
        sys.exit(1)


if __name__ == "__main__":
    main()
