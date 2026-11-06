from typing import Any, Optional, TypedDict


class PatientRoutingState(TypedDict, total=False):

    # -------------------------------------------------
    # Patient input
    # -------------------------------------------------
    top_k: int
    patient_request: dict[str, Any]

    preferred_city: Optional[str]

    preferred_state: Optional[str]
    
    # Temporary report data used during workflow execution.
    # Do not persist this later in production checkpoints.
    report_files: list[dict[str, Any]]

    # -------------------------------------------------
    # Step 8 — PDF parsing
    # -------------------------------------------------

    parse_summary: dict[str, Any]

    document_contexts: list[dict[str, Any]]

    # -------------------------------------------------
    # Step 9 — Medical extraction
    # -------------------------------------------------

    patient_medical_context: dict[str, Any]

    consistency_validation: dict[str, Any]

    # -------------------------------------------------
    # Step 11 — Recommendations
    # -------------------------------------------------

    recommendation_result: dict[str, Any]

    # -------------------------------------------------
    # Clarification / fallback handling
    # -------------------------------------------------

    clarification_required: bool

    clarification_reason: Optional[str]

    clarification_type: Optional[str]

    # -------------------------------------------------
    # Workflow control
    # -------------------------------------------------

    routing_ready: bool

    workflow_status: str

    current_step: str

    # -------------------------------------------------
    # Error handling
    # -------------------------------------------------

    error_message: Optional[str]