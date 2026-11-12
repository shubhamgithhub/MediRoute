"""Nodes of the patient-routing graph.

Ported from Shubham's routing_nodes.py (Step 12, commits 8b23800 / 699a723 on main).

Kept as he built them: ``parse_reports`` (reports in, combined text out), ``recommend_hospitals``
(Step 2 engine), location clarification, finalize and error handling.

Changed for the Step 1 integration: his ``extract_medical_context`` (rule extractor per PDF) and
``validate_medical_context`` nodes are replaced by one ``step1_route`` node that calls the Step 1
voting pipeline on the typed text plus the report text. Its suggested speciality becomes the
``MedicalContext.primary_specialty`` that Step 2 needs; its evidence fills diagnoses/procedures.

Every node logs a ``workflow`` event (same trace file as Step 1) with the workflow id, so one
search can be followed from upload to hospital list.
"""

from __future__ import annotations

import json
from typing import Any

from mediroute.backend.workflow.routing_state import PatientRoutingState
from mediroute.common.medical_context import MedicalContext
from mediroute.specialty_routing.extraction.pdf_parser import PDFParser
from mediroute.specialty_routing.step1.pipeline import ROUTED_DECISIONS
from mediroute.specialty_routing.step1.trace import _trace_logger
from mediroute.utils.logging_config import get_logger

logger = get_logger()
MAX_REPORT_CHARS = 6000  # keeps the Step 1 LLM prompt small


def _log(state: PatientRoutingState, node: str, **data: Any) -> None:
    from datetime import datetime, timezone

    event = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
             "stage": f"workflow:{node}", "request_id": state.get("workflow_id"), **data}
    _trace_logger().info(json.dumps(event, ensure_ascii=False, default=str))
    summary = json.dumps(data, ensure_ascii=False, default=str)
    logger.info("[workflow %s] %s %s", state.get("workflow_id"), node, summary[:240])


class RoutingNodes:
    def __init__(self, step1_service=None, recommendation_engine=None, pdf_parser: PDFParser | None = None):
        self._step1_service = step1_service
        self._engine = recommendation_engine
        self.pdf_parser = pdf_parser or PDFParser()

    # Step 1 and Step 2 load heavy models; resolve them on first use so importing is cheap
    @property
    def step1(self):
        if self._step1_service is None:
            from mediroute.specialty_routing.service import get_service
            self._step1_service = get_service()
        return self._step1_service

    @property
    def engine(self):
        if self._engine is None:
            from mediroute.hospital_recommendation.api import recommendation_engine
            self._engine = recommendation_engine
        return self._engine

    # ================================================
    # REPORT PARSING (optional reports)
    # ================================================
    def parse_reports(self, state: PatientRoutingState) -> dict:
        reports = state.get("report_files") or []
        files = [(r.get("filename"), r.get("content")) for r in reports
                 if isinstance(r, dict) and r.get("filename") and r.get("content")]
        if not files:
            _log(state, "parse_reports", files=0, status="no_reports")
            return {"parse_summary": {"overall_status": "no_reports", "total_files": 0, "successful_files": 0,
                                      "needs_ocr_files": 0, "error_files": 0},
                    "report_text": "", "workflow_status": "reports_skipped", "current_step": "parse_reports"}
        try:
            summary = dict(self.pdf_parser.parse_multiple_pdfs(files))
        except Exception as exc:
            _log(state, "parse_reports", files=len(files), status="error", error=str(exc))
            return {"parse_summary": {"overall_status": "error", "total_files": len(files)},
                    "report_text": "", "workflow_status": "report_parsing_failed",
                    "current_step": "parse_reports", "error_message": None}
        text = (summary.get("combined_text") or "").strip()[:MAX_REPORT_CHARS]
        _log(state, "parse_reports", files=len(files), status=summary.get("overall_status"),
             successful=summary.get("successful_files"), needs_ocr=summary.get("needs_ocr_files"),
             report_chars=len(text), unreadable=summary.get("unreadable_files"))
        return {"parse_summary": summary, "report_text": text, "workflow_status": "reports_parsed",
                "current_step": "parse_reports"}

    # ================================================
    # STEP 1 - SUGGESTED SPECIALITY (voting pipeline)
    # ================================================
    def step1_route(self, state: PatientRoutingState) -> dict:
        from mediroute.specialty_routing.step1.pipeline import Step1Input

        pipeline = getattr(self.step1, "pipeline", None)
        if pipeline is None:
            return {"error_message": "Step 1 voting pipeline is not enabled (MEDIROUTE_ROUTING_MODE=vote).",
                    "current_step": "step1_route"}
        request = state.get("patient_request") or {}
        try:
            result = pipeline.analyze(Step1Input(
                text=request.get("requirement", ""),
                report_text=state.get("report_text", ""),
                clarification=state.get("clarification_answers") or {},
                clarification_round=int(state.get("clarification_round") or 0),
                selected_specialty=state.get("selected_specialty"),
                parent_request_id=state.get("parent_request_id"),
            ))
        except Exception as exc:
            logger.exception("Step 1 failed inside the workflow")
            return {"error_message": f"Step 1 failed: {type(exc).__name__}", "current_step": "step1_route"}

        routed = result["decision"] in ROUTED_DECISIONS and bool(result["suggested_specialty"])
        detail = result.get("evidence_detail") or {}
        context = MedicalContext(
            diagnoses=detail.get("conditions", []),
            procedures=detail.get("procedures", []),
            clinical_findings=detail.get("keyword_matches", []),
            canonical_specialties=[result["suggested_specialty"]] if routed else [],
            primary_specialty=result["suggested_specialty"] if routed else None,
            extraction_status="success" if routed else "needs_clarification",
            clarification_required=not routed,
            clarification_reason=None if routed else result.get("reason"),
        )
        _log(state, "step1_route", step1_request_id=result["request_id"], decision=result["decision"],
             suggested_specialty=result["suggested_specialty"], emergency=result["emergency"],
             evidence=result["evidence"], step1_ms=result["latency_ms"])
        return {
            "step1_result": result,
            "patient_medical_context": context.model_dump(),
            "routing_ready": routed,
            "clarification_required": not routed,
            "clarification_type": None if routed else "medical",
            "clarification_reason": None if routed else result.get("reason"),
            "workflow_status": "specialty_suggested" if routed else "needs_clarification",
            "current_step": "step1_route",
        }

    # ================================================
    # STEP 2 - RECOMMEND HOSPITALS (unchanged engine)
    # ================================================
    def recommend_hospitals(self, state: PatientRoutingState) -> dict:
        if not state.get("routing_ready"):
            return {"workflow_status": "failed", "current_step": "recommend_hospitals",
                    "error_message": "Recommendation attempted without routing readiness."}
        context_data = state.get("patient_medical_context") or {}
        if not context_data:
            return {"recommendation_result": {}, "workflow_status": "failed", "current_step": "recommend_hospitals",
                    "error_message": "Patient medical context is missing."}
        try:
            result = self.engine.recommend(context=MedicalContext(**context_data),
                                           preferred_city=state.get("preferred_city"),
                                           preferred_state=state.get("preferred_state"),
                                           top_k=state.get("top_k", 5))
        except Exception as exc:
            logger.exception("Step 2 recommendation failed")
            return {"recommendation_result": {}, "workflow_status": "failed", "current_step": "recommend_hospitals",
                    "error_message": str(exc)}
        _log(state, "recommend_hospitals", status=result.get("status"),
             specialty=result.get("primary_specialty"), city=state.get("preferred_city"),
             specialty_candidates=result.get("specialty_candidate_count"),
             location_candidates=result.get("location_candidate_count"), count=result.get("count"),
             top=[(r.get("hospital_name") or r.get("name")) for r in (result.get("results") or [])[:5]])
        return {"recommendation_result": result, "workflow_status": result.get("status", "failed"),
                "current_step": "recommend_hospitals", "error_message": None}

    # ================================================
    # CLARIFICATIONS / ENDINGS
    # ================================================
    def create_clarification(self, state: PatientRoutingState) -> dict:
        step1 = state.get("step1_result") or {}
        if step1:  # Step 1 asked a question or offered the speciality list
            reason = step1.get("reason") or "We need a little more information to suggest the right speciality."
            ctype = "specialty_choice" if step1.get("decision") == "needs_user_choice" else "medical"
        else:  # nothing to analyse: no text and no readable report
            reason = state.get("clarification_reason") or (
                "Please describe your healthcare need or upload a readable PDF report.")
            ctype = "report"
        _log(state, "clarification", type=ctype, reason=reason)
        return {"clarification_required": True, "clarification_type": ctype, "clarification_reason": reason,
                "workflow_status": "waiting_for_clarification", "current_step": "clarification"}

    def create_location_clarification(self, state: PatientRoutingState) -> dict:
        reason = ("No matching hospital was found for the selected location. "
                  "Please confirm whether MediRoute may search other locations.")
        _log(state, "location_clarification", city=state.get("preferred_city"))
        return {"clarification_required": True, "clarification_type": "location", "clarification_reason": reason,
                "workflow_status": "waiting_for_clarification", "current_step": "location_clarification"}

    def no_hospital_for_specialty(self, state: PatientRoutingState) -> dict:
        specialty = (state.get("step1_result") or {}).get("suggested_specialty")
        reason = (f"MediRoute does not yet have a verified hospital for {specialty}. "
                  "The suggested speciality is still shown so you can search for it directly.")
        _log(state, "no_hospital_for_specialty", specialty=specialty)
        return {"clarification_required": False, "clarification_type": "no_hospital", "clarification_reason": reason,
                "workflow_status": "no_hospital_for_specialty", "current_step": "completed"}

    def finalize(self, state: PatientRoutingState) -> dict:
        _log(state, "finalize", status="completed")
        return {"clarification_required": False, "workflow_status": "completed", "current_step": "completed"}

    def handle_error(self, state: PatientRoutingState) -> dict:
        _log(state, "error", error=state.get("error_message"))
        return {"workflow_status": "failed", "current_step": "error",
                "error_message": state.get("error_message") or "The MediRoute patient routing workflow failed."}
