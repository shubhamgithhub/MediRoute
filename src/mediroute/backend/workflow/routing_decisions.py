"""Edge decisions of the patient-routing graph.

Ported from Shubham's routing_decisions.py. Changes for the Step 1 integration:

* after report parsing: reports are optional. Typed text alone goes to Step 1; only "reports
  uploaded but none readable and no text" asks for clarification.
* after Step 1 (replaces "after medical validation"): Step 1's decision drives the edge.
* after recommendation: ``no_specialty_match`` ends with a "no verified hospital yet" message
  instead of asking the medical question again (re-asking can't help).
"""

from mediroute.backend.workflow.routing_state import PatientRoutingState


def decide_after_report_parsing(state: PatientRoutingState) -> str:
    """Returns "route" | "clarify" | "error"."""
    if state.get("error_message"):
        return "error"
    has_text = bool((state.get("patient_request") or {}).get("requirement", "").strip())
    has_report_text = bool((state.get("report_text") or "").strip())
    if has_text or has_report_text or state.get("selected_specialty"):
        return "route"
    return "clarify"


def decide_after_step1(state: PatientRoutingState) -> str:
    """Returns "recommend" | "clarify" | "error"."""
    if state.get("error_message"):
        return "error"
    if state.get("routing_ready"):
        return "recommend"
    return "clarify"


def decide_after_recommendation(state: PatientRoutingState) -> str:
    """Returns "finish" | "clarify_location" | "no_hospital" | "clarify_medical" | "error"."""
    if state.get("error_message"):
        return "error"
    result = state.get("recommendation_result")
    if not result:
        return "error"
    status = result.get("status")
    if status == "success":
        return "finish"
    if status == "no_location_match":
        return "clarify_location"
    if status == "no_specialty_match":
        return "no_hospital"
    if status == "needs_clarification":
        return "clarify_medical"
    return "error"
