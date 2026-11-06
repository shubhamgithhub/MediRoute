
"""MediRoute Step 12F — LangGraph routing nodes.

Orchestrates:
Step 8  - PDF parsing
Step 9  - Medical extraction, aggregation, validation
Step 11 - Hospital recommendations
Step 12 - Clarification and workflow control
"""

from typing import Any

from src.Src.backend.workflow.routing_state import (
    PatientRoutingState,
)

from src.Src.backend.medical_context import (
    MedicalContext,
)

from src.Src.backend.services.pdf_parser import (
    PDFParser,
)

from src.Src.backend.services.medical_context_extractor import (
    MedicalContextExtractor,
)

from src.Src.backend.services.patient_context_aggregator import (
    PatientContextAggregator,
)

from src.Src.backend.services.patient_context_validator import (
    PatientContextValidator,
)

from src.Src.backend.services.hospital_recommendation_engine import (
    HospitalRecommendationEngine,
)


class RoutingNodes:

    def __init__(self):

        # Step 8: PDF parsing service
        self.pdf_parser = PDFParser()

        # Step 9: Medical processing services
        self.extractor = MedicalContextExtractor()
        self.aggregator = PatientContextAggregator()
        self.validator = PatientContextValidator()

        # Step 11: Hospital recommendation service
        self.recommendation_engine = (
            HospitalRecommendationEngine()
        )

    # ================================================
    # HELPER METHODS
    # ================================================

    @staticmethod
    def _as_dict(value: Any) -> dict:
        """Convert Pydantic models or mappings to dict."""

        if isinstance(value, dict):
            return value

        if hasattr(value, "model_dump"):
            return value.model_dump()

        return dict(value)

    @staticmethod
    def _failed_context(reason: str) -> MedicalContext:
        """Create context for an unreadable report."""

        return MedicalContext(
            extraction_status="failed",
            clarification_required=True,
            clarification_reason=reason,
        )

    # ================================================
    # STEP 8 — PARSE ALL MEDICAL REPORTS
    # ================================================

    def parse_reports(
        self,
        state: PatientRoutingState
    ) -> dict:

        reports = state.get("report_files") or []

        files = [
            (
                report.get("filename"),
                report.get("content"),
            )
            for report in reports
            if (
                isinstance(report, dict)
                and report.get("filename")
                and report.get("content")
            )
        ]

        # No valid reports supplied
        if not files:

            return {
                "parse_summary": {
                    "overall_status": "error",
                    "total_files": 0,
                    "successful_files": 0,
                    "needs_ocr_files": 0,
                    "error_files": 0,
                    "combined_text": "",
                },
                "clarification_required": True,
                "clarification_type": "report",
                "clarification_reason": (
                    "No valid medical PDF reports "
                    "were provided."
                ),
                "routing_ready": False,
                "workflow_status": "report_parsing_failed",
                "current_step": "parse_reports",
                "error_message": None,
            }

        try:

            summary = (
                self.pdf_parser.parse_multiple_pdfs(files)
            )

            return {
                "parse_summary": self._as_dict(summary),
                "workflow_status": "reports_parsed",
                "current_step": "parse_reports",
                "error_message": None,
            }

        except Exception as exc:

            return {
                "parse_summary": {
                    "overall_status": "error",
                    "combined_text": "",
                },
                "clarification_required": True,
                "clarification_type": "report",
                "clarification_reason": (
                    "The medical reports could "
                    "not be processed."
                ),
                "routing_ready": False,
                "workflow_status": "report_parsing_failed",
                "current_step": "parse_reports",
                "error_message": str(exc),
            }

    # ================================================
    # STEP 9 — EXTRACT EACH PDF SEPARATELY
    # ================================================

    def extract_medical_context(
        self,
        state: PatientRoutingState
    ) -> dict:

        reports = state.get("report_files") or []

        document_contexts = []
        contexts = []

        try:

            # Process each uploaded PDF individually
            for report in reports:

                filename = report.get(
                    "filename",
                    "unknown.pdf"
                )

                content = report.get("content")

                if not content:

                    parsed = {
                        "status": "error",
                        "text": "",
                    }

                else:

                    parsed = self._as_dict(
                        self.pdf_parser.parse_pdf_bytes(
                            content,
                            filename,
                        )
                    )

                parse_status = parsed.get(
                    "status",
                    "error"
                )

                # Read the text from the parser result
                extracted_text = (
                    parsed.get("text")
                    or parsed.get("extracted_text")
                    or parsed.get("combined_text")
                    or ""
                )

                # Extract medical context from readable PDF
                if (
                    parse_status == "success"
                    and extracted_text.strip()
                ):

                    extracted = self.extractor.extract(
                        extracted_text
                    )

                    if isinstance(
                        extracted,
                        MedicalContext
                    ):
                        context = extracted

                    else:
                        context = MedicalContext(
                            **self._as_dict(extracted)
                        )

                else:

                    # Keep failed reports in the document set
                    # so the validator can detect incomplete data.
                    context = self._failed_context(
                        f"Report '{filename}' could not "
                        f"be read reliably "
                        f"(parser status: {parse_status})."
                    )

                contexts.append(context)

                document_contexts.append({
                    "filename": filename,
                    "parse_status": parse_status,
                    "medical_context": context.model_dump(),
                })

            # ========================================
            # NO REPORTS
            # ========================================

            if not contexts:

                return {
                    "document_contexts": [],
                    "patient_medical_context": {},
                    "consistency_validation": {
                        "status": "needs_review",
                        "routing_ready": False,
                        "clarification_required": True,
                        "reason": (
                            "No medical reports were provided."
                        ),
                    },
                    "routing_ready": False,
                    "clarification_required": True,
                    "clarification_type": "report",
                    "clarification_reason": (
                        "No medical reports were provided."
                    ),
                    "workflow_status": (
                        "medical_extraction_failed"
                    ),
                    "current_step": (
                        "extract_medical_context"
                    ),
                    "error_message": None,
                }

            # ========================================
            # AGGREGATE MEDICAL CONTEXTS
            # ========================================

            aggregated_context = (
                self.aggregator.aggregate(contexts)
            )

            # ========================================
            # VALIDATE CONSISTENCY
            # ========================================

            # Validator needs BOTH:
            # 1. Individual report contexts
            # 2. Aggregated patient context

            validation = self.validator.validate(
                contexts,
                aggregated_context,
            )

            aggregate_dict = self._as_dict(
                aggregated_context
            )

            validation_dict = self._as_dict(
                validation
            )

            routing_ready = bool(
                validation_dict.get(
                    "routing_ready",
                    False
                )
            )

            clarification_required = (
                not routing_ready
                or bool(
                    validation_dict.get(
                        "clarification_required",
                        False
                    )
                )
            )

            reason = validation_dict.get("reason")

            if clarification_required and not reason:
                reason = (
                    "Medical information needs "
                    "clarification before hospital routing."
                )

            # ========================================
            # RETURN MEDICAL RESULTS TO LANGGRAPH
            # ========================================

            return {
                "document_contexts": document_contexts,
                "patient_medical_context": aggregate_dict,
                "consistency_validation": validation_dict,
                "routing_ready": routing_ready,
                "clarification_required": (
                    clarification_required
                ),
                "clarification_type": (
                    "medical_context"
                    if clarification_required
                    else None
                ),
                "clarification_reason": reason,
                "workflow_status": (
                    "medical_context_extracted"
                ),
                "current_step": (
                    "extract_medical_context"
                ),
                "error_message": None,
            }

        except Exception as exc:

            # Programming/integration errors are routed
            # to the graph's error node.
            return {
                "document_contexts": document_contexts,
                "patient_medical_context": {},
                "consistency_validation": {
                    "status": "failed",
                    "routing_ready": False,
                    "clarification_required": True,
                    "reason": (
                        "Medical processing failed."
                    ),
                },
                "routing_ready": False,
                "clarification_required": True,
                "clarification_type": "medical_context",
                "clarification_reason": (
                    "Medical reports could not "
                    "be processed."
                ),
                "workflow_status": (
                    "medical_extraction_failed"
                ),
                "current_step": (
                    "extract_medical_context"
                ),
                "error_message": str(exc),
            }

    # ================================================
    # STEP 9 — VALIDATE ROUTING READINESS
    # ================================================

    def validate_medical_context(
        self,
        state: PatientRoutingState
    ) -> dict:

        if state.get("error_message"):

            return {
                "routing_ready": False,
                "workflow_status": "failed",
                "current_step": (
                    "validate_medical_context"
                ),
            }

        validation = (
            state.get("consistency_validation") or {}
        )

        if not validation:

            return {
                "routing_ready": False,
                "clarification_required": True,
                "clarification_type": "medical_context",
                "clarification_reason": (
                    "Medical context validation is missing."
                ),
                "workflow_status": (
                    "needs_clarification"
                ),
                "current_step": (
                    "validate_medical_context"
                ),
            }

        # If validator rejects routing, ask for clarification
        if not validation.get(
            "routing_ready",
            False
        ):

            return {
                "routing_ready": False,
                "clarification_required": True,
                "clarification_type": (
                    state.get("clarification_type")
                    or "medical_context"
                ),
                "clarification_reason": (
                    validation.get("reason")
                    or state.get("clarification_reason")
                    or "Medical information needs clarification."
                ),
                "workflow_status": (
                    "needs_clarification"
                ),
                "current_step": (
                    "validate_medical_context"
                ),
            }

        # Medical information is routable
        return {
            "routing_ready": True,
            "clarification_required": False,
            "clarification_type": None,
            "clarification_reason": None,
            "workflow_status": (
                "medical_context_validated"
            ),
            "current_step": (
                "validate_medical_context"
            ),
        }

    # ================================================
    # STEP 11 — RECOMMEND HOSPITALS
    # ================================================

    def recommend_hospitals(
        self,
        state: PatientRoutingState
    ) -> dict:

        # Never recommend before validation
        if not state.get(
            "routing_ready",
            False
        ):

            return {
                "workflow_status": "failed",
                "current_step": "recommend_hospitals",
                "error_message": (
                    "Recommendation attempted "
                    "without routing readiness."
                ),
            }

        context_data = (
            state.get("patient_medical_context") or {}
        )

        if not context_data:

            return {
                "recommendation_result": {},
                "workflow_status": "failed",
                "current_step": "recommend_hospitals",
                "error_message": (
                    "Patient medical context is missing."
                ),
            }

        try:

            context = MedicalContext(
                **context_data
            )

            result = (
                self.recommendation_engine.recommend(
                    context=context,
                    preferred_city=state.get(
                        "preferred_city"
                    ),
                    preferred_state=state.get(
                        "preferred_state"
                    ),
                    top_k=state.get(
                        "top_k",
                        5
                    ),
                )
            )

            return {
                "recommendation_result": result,
                "workflow_status": result.get(
                    "status",
                    "failed"
                ),
                "current_step": "recommend_hospitals",
                "error_message": None,
            }

        except Exception as exc:

            return {
                "recommendation_result": {},
                "workflow_status": "failed",
                "current_step": "recommend_hospitals",
                "error_message": str(exc),
            }

    # ================================================
    # MEDICAL / REPORT CLARIFICATION
    # ================================================

    def create_clarification(
        self,
        state: PatientRoutingState
    ) -> dict:

        clarification_type = state.get(
            "clarification_type"
        )

        reason = state.get(
            "clarification_reason"
        )

        if clarification_type == "report":

            message = reason or (
                "One or more medical reports could "
                "not be read. Please upload clearer "
                "PDFs or supply the information manually."
            )

        else:

            message = reason or (
                "Additional medical information or "
                "treatment priority is required before "
                "MediRoute can recommend hospitals."
            )

        return {
            "clarification_required": True,
            "clarification_reason": message,
            "workflow_status": (
                "waiting_for_clarification"
            ),
            "current_step": "clarification",
        }

    # ================================================
    # LOCATION CLARIFICATION
    # ================================================

    def create_location_clarification(
        self,
        state: PatientRoutingState
    ) -> dict:

        return {
            "clarification_required": True,
            "clarification_type": "location",
            "clarification_reason": (
                "No matching hospital was found "
                "for the selected location. "
                "Please confirm whether MediRoute "
                "may search other locations."
            ),
            "workflow_status": (
                "waiting_for_clarification"
            ),
            "current_step": (
                "location_clarification"
            ),
        }

    # ================================================
    # SUCCESSFUL COMPLETION
    # ================================================

    def finalize(
        self,
        state: PatientRoutingState
    ) -> dict:

        return {
            "clarification_required": False,
            "workflow_status": "completed",
            "current_step": "completed",
        }

    # ================================================
    # WORKFLOW ERROR HANDLING
    # ================================================

    def handle_error(
        self,
        state: PatientRoutingState
    ) -> dict:

        return {
            "workflow_status": "failed",
            "current_step": "error",
            "error_message": (
                state.get("error_message")
                or "The MediRoute patient routing workflow failed."
            ),
        }
