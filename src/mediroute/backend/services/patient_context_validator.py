from mediroute.backend.medical_context import MedicalContext


class PatientContextValidator:

    def validate(
        self,
        document_contexts: list[MedicalContext],
        aggregated_context: MedicalContext
    ) -> dict:

        document_specialties = []

        failed_reports = 0
        review_reports = 0

        for context in document_contexts:

            if context.extraction_status == "failed":
                failed_reports += 1

            if context.extraction_status == "needs_review":
                review_reports += 1

            for specialty in context.canonical_specialties:

                if specialty not in document_specialties:
                    document_specialties.append(
                        specialty
                    )

        # No routable specialty
        if not document_specialties:

            return {
                "consistency_status": "needs_review",
                "clarification_required": True,
                "routing_ready": False,
                "reason": (
                    "No routable specialty was identified "
                    "across the uploaded reports"
                ),
                "specialties_found": []
            }

        # Multiple specialties
        if len(document_specialties) > 1:

            return {
                "consistency_status": "conflict",
                "clarification_required": True,
                "routing_ready": False,
                "reason": (
                    "Uploaded reports suggest multiple "
                    "different specialties"
                ),
                "specialties_found": document_specialties
            }

        # Same specialty but some reports need review
        if failed_reports > 0 or review_reports > 0:

            return {
                "consistency_status": "partial",
                "clarification_required": True,
                "routing_ready": False,
                "reason": (
                    "Reports agree on the main specialty, "
                    "but some reports require review"
                ),
                "specialties_found": document_specialties
            }

        # Fully consistent
        return {
            "consistency_status": "consistent",
            "clarification_required": False,
            "routing_ready": True,
            "reason": None,
            "specialties_found": document_specialties
        }