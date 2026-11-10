"""End-to-end endpoint: POST /api/patient-routing (reports + text -> Step 1 -> Step 2).

Ported from Shubham's Step 12H endpoint (main.py on main, commit 8b23800): same path, same
multipart input and upload checks, same response fields. Added for the Step 1 integration:

* reports are optional (typed text alone works);
* Step 1 follow-up fields: clarification answers, round, chosen speciality, parent request id;
* ``step1`` block in the response (suggested speciality, evidence, emergency notice,
  clarification form or speciality list, request id) and a ``workflow_id`` for the logs.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from mediroute.backend.workflow.patient_routing_graph import PatientRoutingGraph
from mediroute.utils.logging_config import get_logger

logger = get_logger()
router = APIRouter(tags=["Workflow - Step 1 + Step 2"])

MAX_REPORTS = 5
MAX_PDF_BYTES = 10 * 1024 * 1024  # 10 MB per report
MAX_TOTAL_BYTES = 30 * 1024 * 1024

_graph: PatientRoutingGraph | None = None


def get_graph() -> PatientRoutingGraph:
    global _graph
    if _graph is None:
        _graph = PatientRoutingGraph()
    return _graph


async def _read_reports(files: list[UploadFile]) -> list[dict]:
    if len(files) > MAX_REPORTS:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_REPORTS} PDF reports are allowed per request.")
    reports, total = [], 0
    for upload in files:
        filename = Path((upload.filename or "unnamed.pdf").replace("\\", "/")).name
        if not filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Only PDF files are supported.")
        try:
            content = await upload.read(MAX_PDF_BYTES + 1)
        finally:
            await upload.close()
        if len(content) > MAX_PDF_BYTES:
            raise HTTPException(status_code=413,
                                detail=f"PDF exceeds the {MAX_PDF_BYTES // (1024 * 1024)} MB per-file limit.")
        total += len(content)
        if total > MAX_TOTAL_BYTES:
            raise HTTPException(status_code=413, detail="Total uploaded PDF size exceeds 30 MB.")
        # Basic PDF signature check; not a replacement for production security scanning.
        if not content.startswith(b"%PDF-"):
            raise HTTPException(status_code=400, detail=f"Invalid PDF file: {filename}")
        reports.append({"filename": filename, "content": content})
    return reports


def _step1_view(step1: dict | None) -> dict | None:
    """The Step 1 fields the frontend needs (debug-only fields left out)."""
    if not step1:
        return None
    keys = ("request_id", "parent_request_id", "decision", "suggested_specialty", "suggested_specialty_label",
            "care_category", "in_hospital_data", "evidence", "evidence_detail", "reason", "emergency",
            "emergency_message", "clarification_required", "clarification", "user_choice", "disclaimer",
            "latency_ms")
    return {k: step1.get(k) for k in keys}


@router.post("/api/patient-routing")
async def run_patient_routing(
    files: list[UploadFile] | None = File(default=None, description="Optional PDF medical reports (max 5)"),
    requirement: str = Form(default="", description="What the patient types"),
    preferred_city: str | None = Form(default=None),
    preferred_state: str | None = Form(default=None),
    top_k: int = Form(default=5, ge=1, le=20),
    language: str = Form(default="English"),
    clarification_body_area: str = Form(default=""),
    clarification_existing_diagnosis: str = Form(default=""),
    clarification_recommended_procedure: str = Form(default=""),
    clarification_round: int = Form(default=0, ge=0, le=5),
    selected_specialty: str | None = Form(default=None),
    parent_request_id: str | None = Form(default=None),
):
    """Run the complete workflow: optional reports -> Step 1 (suggested speciality) -> Step 2
    (ranked hospitals), or return a clarification. Raw PDF bytes are never returned."""
    report_files = await _read_reports(files or [])
    workflow_id = uuid.uuid4().hex[:12]
    answers = {"body_area": clarification_body_area, "existing_diagnosis": clarification_existing_diagnosis,
               "recommended_procedure": clarification_recommended_procedure}
    initial_state = {
        "workflow_id": workflow_id,
        "patient_request": {"requirement": requirement, "language": language},
        "report_files": report_files,
        "preferred_city": preferred_city,
        "preferred_state": preferred_state,
        "top_k": top_k,
        "clarification_answers": {k: v for k, v in answers.items() if v.strip()},
        "clarification_round": clarification_round,
        "selected_specialty": selected_specialty or None,
        "parent_request_id": parent_request_id or None,
        "workflow_status": "started",
        "current_step": "start",
        "routing_ready": False,
        "clarification_required": False,
        "clarification_reason": None,
        "error_message": None,
    }
    logger.info("[workflow %s] start reports=%d text_chars=%d city=%s round=%d selected=%s parent=%s",
                workflow_id, len(report_files), len(requirement), preferred_city, clarification_round,
                selected_specialty, parent_request_id)
    try:
        # The graph is synchronous and runs model inference; keep it off the event loop.
        result = await run_in_threadpool(get_graph().invoke, initial_state)
    except Exception:
        logger.exception("[workflow %s] patient-routing execution failed", workflow_id)
        return JSONResponse(status_code=500, content={"workflow_status": "failed", "workflow_id": workflow_id,
                                                      "message": "An internal routing error occurred."})

    workflow_status = result.get("workflow_status", "failed")
    if workflow_status == "failed":
        logger.error("[workflow %s] ended in failed state: %s", workflow_id, result.get("error_message"))
        return JSONResponse(status_code=500, content=jsonable_encoder({
            "workflow_status": "failed", "workflow_id": workflow_id,
            "message": "MediRoute could not complete the routing workflow."}))

    parse = result.get("parse_summary") or {}
    # Never return result["report_files"]: it holds the uploaded PDF bytes.
    response = {
        "workflow_id": workflow_id,
        "workflow_status": workflow_status,
        "current_step": result.get("current_step"),
        "routing_ready": result.get("routing_ready", False),
        "parse_summary": {k: parse.get(k) for k in ("overall_status", "total_files", "successful_files",
                                                     "needs_ocr_files", "error_files")},
        "step1": _step1_view(result.get("step1_result")),
        "patient_medical_context": result.get("patient_medical_context"),
        "clarification_required": result.get("clarification_required", False),
        "clarification_type": result.get("clarification_type"),
        "clarification_reason": result.get("clarification_reason"),
        "recommendation_result": result.get("recommendation_result") or {},
    }
    logger.info("[workflow %s] done status=%s step1=%s specialty=%s hospitals=%s", workflow_id, workflow_status,
                (response["step1"] or {}).get("decision"), (response["step1"] or {}).get("suggested_specialty"),
                response["recommendation_result"].get("count"))
    return jsonable_encoder(response)
