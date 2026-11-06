from src.Src.backend.workflow.patient_routing_graph import (
    PatientRoutingGraph,
)


def run_tests():

    print()
    print(
        "STEP 12D — LANGGRAPH WORKFLOW TEST"
    )
    print("=" * 60)

    graph = PatientRoutingGraph()

    passed = 0
    failed = 0

    # -------------------------------------------------
    # T001 — valid medical context
    # -------------------------------------------------

    state = {
        "patient_medical_context": {
            "diagnoses": [
                "coronary artery disease"
            ],
            "symptoms": [
                "chest pain"
            ],
            "procedures": [
                "CABG"
            ],
            "medications": [],
            "clinical_findings": [],
            "icd10_codes": [
                "I25"
            ],
            "canonical_specialties": [
                "Cardiology"
            ],
            "primary_specialty":
                "Cardiology",
            "extraction_status":
                "success",
            "clarification_required":
                False,
            "clarification_reason":
                None,
        },

        "consistency_validation": {
            "status": "consistent",
            "routing_ready": True,
            "clarification_required":
                False,
        },

        "preferred_city": None,
        "preferred_state": None,

        "clarification_required":
            False,

        "routing_ready":
            False,

        "workflow_status":
            "started",

        "current_step":
            "start",
    }

    result = graph.invoke(
        state
    )

    if (
        result.get(
            "workflow_status"
        )
        == "completed"
    ):
        print(
            "T001 PASS - valid workflow completed"
        )
        passed += 1
    else:
        print(
            "T001 FAIL - valid workflow did not complete"
        )
        print(result)
        failed += 1

    # -------------------------------------------------
    # T002 — invalid context → clarification
    # -------------------------------------------------

    invalid_state = {
        "patient_medical_context": {},
        "consistency_validation": {
            "status": "needs_review",
            "routing_ready": False,
            "clarification_required":
                True,
            "reason":
                "No routable specialty identified.",
        },
        "clarification_required":
            False,
        "routing_ready":
            False,
        "workflow_status":
            "started",
        "current_step":
            "start",
    }

    invalid_result = graph.invoke(
        invalid_state
    )

    if (
        invalid_result.get(
            "workflow_status"
        )
        == "waiting_for_clarification"
    ):
        print(
            "T002 PASS - invalid context routed to clarification"
        )
        passed += 1
    else:
        print(
            "T002 FAIL"
        )
        print(
            invalid_result
        )
        failed += 1

    # -------------------------------------------------
    # Summary
    # -------------------------------------------------

    total = passed + failed

    print()
    print("=" * 60)
    print(
        f"Total tests: {total}"
    )
    print(
        f"Passed: {passed}"
    )
    print(
        f"Failed: {failed}"
    )


if __name__ == "__main__":
    run_tests()