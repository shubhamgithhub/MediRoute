from src.Src.backend.medical_context import MedicalContext


class SemanticQueryBuilder:

    def build(
        self,
        context: MedicalContext
    ) -> str:

        parts = []

        # ---------------------------------------------
        # Primary specialty
        # ---------------------------------------------

        if context.primary_specialty:

            parts.append(
                f"Specialty: "
                f"{context.primary_specialty}"
            )

        # ---------------------------------------------
        # Diagnoses
        # ---------------------------------------------

        if context.diagnoses:

            parts.append(
                "Diagnoses: "
                + ", ".join(
                    context.diagnoses
                )
            )

        # ---------------------------------------------
        # Procedures
        # ---------------------------------------------

        if context.procedures:

            parts.append(
                "Relevant procedures: "
                + ", ".join(
                    context.procedures
                )
            )

        # ---------------------------------------------
        # Clinical findings
        # ---------------------------------------------

        if context.clinical_findings:

            parts.append(
                "Clinical findings: "
                + ", ".join(
                    context.clinical_findings
                )
            )

        # ---------------------------------------------
        # Symptoms
        # ---------------------------------------------

        if context.symptoms:

            parts.append(
                "Symptoms: "
                + ", ".join(
                    context.symptoms
                )
            )

        # ---------------------------------------------
        # ICD-10 codes
        # ---------------------------------------------

        if context.icd10_codes:

            parts.append(
                "ICD-10: "
                + ", ".join(
                    context.icd10_codes
                )
            )

        return ". ".join(
            parts
        )