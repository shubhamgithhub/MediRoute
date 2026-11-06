
import sys
from pathlib import Path

import pymupdf

from src.Src.backend.workflow.patient_routing_graph import (
    PatientRoutingGraph,
)


def create_blank_pdf():
    """Generate a valid PDF with no extractable text."""
    doc = pymupdf.open()
    doc.new_page()
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def create_state(reports):
    return {
        "report_files": reports,
        "patient_request": {
            "requirement": "Cardiac treatment"
        },
        "preferred_city": None,
        "preferred_state": None,
        "workflow_status": "started",
        "current_step": "start",
        "clarification_required": False,
        "routing_ready": False,
        "error_message": None,
    }


def run_case(graph, name, reports):
    result = graph.invoke(create_state(reports))

    medical = result.get("patient_medical_context") or {}
    parse = result.get("parse_summary") or {}
    recommendation = result.get("recommendation_result") or {}

    print(f"\n{name}")
    print("=" * 55)
    print("Parsing:", parse.get("overall_status"))
    print("Workflow:", result.get("workflow_status"))
    print("Diagnoses:", medical.get("diagnoses"))
    print("Routing ready:", result.get("routing_ready"))
    print("Clarification:", result.get("clarification_reason"))
    print("Recommendations:", recommendation.get("count", 0))
    print("Error:", result.get("error_message"))

    return result


def is_clarification(result):
    recommendation = result.get("recommendation_result") or {}

    return (
        result.get("workflow_status")
        == "waiting_for_clarification"
        and result.get("clarification_required") is True
        and result.get("routing_ready") is False
        and recommendation.get("count", 0) == 0
        and not result.get("error_message")
    )


def main():
    if len(sys.argv) != 2:
        print(
            "Usage: python -m "
            "src.Src.backend.workflow.test_step12g "
            "<readable_cardiac_pdf>"
        )
        sys.exit(2)

    cardiac_path = Path(sys.argv[1])

    if not cardiac_path.is_file():
        print(f"File not found: {cardiac_path}")
        sys.exit(2)

    cardiac_report = {
        "filename": cardiac_path.name,
        "content": cardiac_path.read_bytes(),
    }

    blank_report = {
        "filename": "synthetic_blank.pdf",
        "content": create_blank_pdf(),
    }

    graph = PatientRoutingGraph()

    # T001: One readable + one blank PDF
    partial = run_case(
        graph,
        "T001 - Readable cardiac PDF + blank PDF",
        [cardiac_report, blank_report],
    )

    # T002: Only a blank PDF
    blank = run_case(
        graph,
        "T002 - Blank PDF only",
        [blank_report],
    )

    # T003: No PDF supplied
    missing = run_case(
        graph,
        "T003 - No PDF supplied",
        [],
    )

    partial_medical = (
        partial.get("patient_medical_context") or {}
    )

    checks = [
        (
            "T001 partial document clarification",
            is_clarification(partial)
            and "coronary artery disease"
            in partial_medical.get("diagnoses", []),
        ),
        (
            "T002 blank document clarification",
            is_clarification(blank),
        ),
        (
            "T003 missing document clarification",
            is_clarification(missing),
        ),
    ]

    print("\nSTEP 12G TEST SUMMARY")
    print("=" * 55)

    passed = 0

    for label, success in checks:
        print(
            f"{'PASS' if success else 'FAIL'} - {label}"
        )
        passed += int(success)

    print(f"\nPassed: {passed}/{len(checks)}")

    if passed != len(checks):
        sys.exit(1)


if __name__ == "__main__":
    main()
