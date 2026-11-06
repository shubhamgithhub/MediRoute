from pathlib import Path

from src.Src.backend.workflow.patient_routing_graph import (
    PatientRoutingGraph,
)

# Project root: MediRoute
PROJECT_ROOT = Path(__file__).resolve().parents[4]

# Change this path to an existing readable cardiac PDF.
PDF_FILE = PROJECT_ROOT / "Data" / "MediRoute_Report_01_Coronary_Artery_Disease.pdf"


def main():

    if not PDF_FILE.exists():
        print(f"TEST BLOCKED: PDF not found at {PDF_FILE}")
        return

    graph = PatientRoutingGraph()

    state = {
        "report_files": [
            {
                "filename": PDF_FILE.name,
                "content": PDF_FILE.read_bytes(),
            }
        ],
        "patient_request": {
            "requirement": "Cardiac treatment"
        },
        "preferred_city": None,
        "preferred_state": None,
        "workflow_status": "started",
        "current_step": "start",
        "clarification_required": False,
        "routing_ready": False,
    }

    result = graph.invoke(state)

    print("\nSTEP 12E — END-TO-END TEST")
    print("=" * 50)

    print("Workflow status:", result.get("workflow_status"))
    print("Current step:", result.get("current_step"))

    parse_result = result.get("parse_summary", {})
    print("PDF parsing:", parse_result.get("overall_status"))

    context = result.get("patient_medical_context", {})
    print("Diagnoses:", context.get("diagnoses"))
    print("Primary specialty:", context.get("primary_specialty"))

    validation = result.get("consistency_validation", {})
    print("Routing ready:", validation.get("routing_ready"))

    recommendation = result.get("recommendation_result", {})
    print("Recommendation status:", recommendation.get("status"))
    print("Hospital count:", recommendation.get("count", 0))

    if result.get("clarification_required"):
        print("Clarification:", result.get("clarification_reason"))

    if result.get("error_message"):
        print("Error:", result.get("error_message"))

    if (
        result.get("workflow_status") == "completed"
        and recommendation.get("count", 0) > 0
    ):
        print("\nPASS — Full patient routing workflow completed")
    else:
        print("\nNOT COMPLETED — Review the statuses above")


if __name__ == "__main__":
    main()