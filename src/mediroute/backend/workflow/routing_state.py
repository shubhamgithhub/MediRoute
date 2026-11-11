"""State passed between the nodes of the patient-routing graph (LangGraph).

Ported from Shubham's Step 12 workflow (commits 8b23800, 699a723 on main) and extended for the
Step 1 voting pipeline: the medical step is one Step 1 node instead of extract + validate.
"""

from typing import Any, Optional, TypedDict


class PatientRoutingState(TypedDict, total=False):

    # -------------------------------------------------
    # Patient input
    # -------------------------------------------------
    patient_request: dict[str, Any]  # requirement, language, ...
    preferred_city: Optional[str]
    preferred_state: Optional[str]
    top_k: int

    # Temporary report data used during workflow execution.
    # Never returned by the API and never persisted.
    report_files: list[dict[str, Any]]

    # Step 1 follow-up input (clarification rounds of one search)
    clarification_answers: dict[str, str]
    clarification_round: int
    selected_specialty: Optional[str]
    parent_request_id: Optional[str]

    # -------------------------------------------------
    # Report parsing
    # -------------------------------------------------
    parse_summary: dict[str, Any]
    report_text: str

    # -------------------------------------------------
    # Step 1 - suggested speciality (voting pipeline)
    # -------------------------------------------------
    step1_result: dict[str, Any]
    patient_medical_context: dict[str, Any]  # MedicalContext handed to Step 2

    # -------------------------------------------------
    # Step 2 - recommendations
    # -------------------------------------------------
    recommendation_result: dict[str, Any]

    # -------------------------------------------------
    # Clarification / fallback handling
    # -------------------------------------------------
    clarification_required: bool
    clarification_reason: Optional[str]
    clarification_type: Optional[str]  # report | medical | location | no_hospital

    # -------------------------------------------------
    # Workflow control
    # -------------------------------------------------
    workflow_id: str  # one id per /api/patient-routing call, in every workflow log event
    routing_ready: bool
    workflow_status: str
    current_step: str
    error_message: Optional[str]
