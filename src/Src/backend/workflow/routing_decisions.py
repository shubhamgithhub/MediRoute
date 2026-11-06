from src.Src.backend.workflow.routing_state import (
    PatientRoutingState,
)


def decide_after_medical_validation(
    state: PatientRoutingState
) -> str:

    """
    Decide what happens after medical-context validation.

    Returns one of:
    - "recommend"
    - "clarify"
    - "error"
    """

    if state.get("error_message"):
        return "error"

    if state.get(
        "clarification_required",
        False
    ):
        return "clarify"

    if state.get(
        "routing_ready",
        False
    ):
        return "recommend"

    return "clarify"


def decide_after_recommendation(
    state: PatientRoutingState
) -> str:

    """
    Decide what happens after Step 11 recommendation.

    Returns one of:
    - "finish"
    - "clarify_location"
    - "clarify_medical"
    - "error"
    """

    if state.get("error_message"):
        return "error"

    result = state.get(
        "recommendation_result"
    )

    if not result:
        return "error"

    status = result.get(
        "status"
    )

    if status == "success":
        return "finish"

    if status == "no_location_match":
        return "clarify_location"

    if status in {
        "needs_clarification",
        "no_specialty_match",
    }:
        return "clarify_medical"

    return "error"


def decide_after_report_parsing(state: PatientRoutingState) -> str:

    if state.get("error_message"):
        return "error"

    parse_result = state.get("parse_summary") or {}
    status = parse_result.get("overall_status")

    if status in {"success", "partial_success"}:
        if (parse_result.get("combined_text") or "").strip():
            return "extract"

    return "clarify"
