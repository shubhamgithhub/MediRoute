from src.Src.backend.workflow.routing_decisions import (
    decide_after_medical_validation,
    decide_after_recommendation,
)


def run_tests():

    passed = 0
    failed = 0

    # T001
    state = {
        "routing_ready": True,
        "clarification_required": False,
    }

    if (
        decide_after_medical_validation(
            state
        )
        == "recommend"
    ):
        print(
            "T001 PASS - valid context routes to recommendation"
        )
        passed += 1
    else:
        print("T001 FAIL")
        failed += 1

    # T002
    state = {
        "routing_ready": False,
        "clarification_required": True,
    }

    if (
        decide_after_medical_validation(
            state
        )
        == "clarify"
    ):
        print(
            "T002 PASS - invalid context routes to clarification"
        )
        passed += 1
    else:
        print("T002 FAIL")
        failed += 1

    # T003
    state = {
        "recommendation_result": {
            "status": "success"
        }
    }

    if (
        decide_after_recommendation(
            state
        )
        == "finish"
    ):
        print(
            "T003 PASS - successful recommendation finishes"
        )
        passed += 1
    else:
        print("T003 FAIL")
        failed += 1

    # T004
    state = {
        "recommendation_result": {
            "status": "no_location_match"
        }
    }

    if (
        decide_after_recommendation(
            state
        )
        == "clarify_location"
    ):
        print(
            "T004 PASS - location failure routes to clarification"
        )
        passed += 1
    else:
        print("T004 FAIL")
        failed += 1

    # T005
    state = {
        "error_message":
            "Unexpected workflow error"
    }

    if (
        decide_after_medical_validation(
            state
        )
        == "error"
    ):
        print(
            "T005 PASS - error routes to error node"
        )
        passed += 1
    else:
        print("T005 FAIL")
        failed += 1

    total = passed + failed

    print()
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