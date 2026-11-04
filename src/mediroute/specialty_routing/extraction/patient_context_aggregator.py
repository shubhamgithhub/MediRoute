from mediroute.common.medical_context import MedicalContext


class PatientContextAggregator:

    def aggregate(
        self,
        contexts: list[MedicalContext]
    ) -> MedicalContext:

        if not contexts:
            return MedicalContext(
                extraction_status="failed",
                clarification_required=True,
                clarification_reason=(
                    "No medical contexts available "
                    "for aggregation"
                )
            )

        diagnoses = []
        symptoms = []
        procedures = []
        medications = []
        clinical_findings = []
        icd10_codes = []
        canonical_specialties = []

        clarification_reasons = []

        successful_contexts = 0
        review_contexts = 0
        failed_contexts = 0

        for context in contexts:

            diagnoses.extend(
                context.diagnoses
            )

            symptoms.extend(
                context.symptoms
            )

            procedures.extend(
                context.procedures
            )

            medications.extend(
                context.medications
            )

            clinical_findings.extend(
                context.clinical_findings
            )

            icd10_codes.extend(
                context.icd10_codes
            )

            canonical_specialties.extend(
                context.canonical_specialties
            )

            if context.extraction_status == "success":
                successful_contexts += 1

            elif context.extraction_status == "needs_review":
                review_contexts += 1

            elif context.extraction_status == "failed":
                failed_contexts += 1

            if context.clarification_reason:
                clarification_reasons.append(
                    context.clarification_reason
                )

        # Remove duplicates while preserving order
        diagnoses = list(
            dict.fromkeys(diagnoses)
        )

        symptoms = list(
            dict.fromkeys(symptoms)
        )

        procedures = list(
            dict.fromkeys(procedures)
        )

        medications = list(
            dict.fromkeys(medications)
        )

        clinical_findings = list(
            dict.fromkeys(clinical_findings)
        )

        icd10_codes = list(
            dict.fromkeys(icd10_codes)
        )

        canonical_specialties = list(
            dict.fromkeys(canonical_specialties)
        )

        primary_specialty = (
            canonical_specialties[0]
            if canonical_specialties
            else None
        )

        # --------------------------------------
        # Patient-level validation
        # --------------------------------------

        if successful_contexts > 0:

            if review_contexts > 0 or failed_contexts > 0:

                extraction_status = "partial_success"

                clarification_required = True

                clarification_reason = (
                    "Some reports were successfully "
                    "processed, but other reports "
                    "require review"
                )

            else:

                extraction_status = "success"

                clarification_required = False

                clarification_reason = None

        elif review_contexts > 0:

            extraction_status = "needs_review"

            clarification_required = True

            clarification_reason = (
                "Medical information was found, "
                "but patient routing requires review"
            )

        else:

            extraction_status = "failed"

            clarification_required = True

            clarification_reason = (
                "No usable medical context "
                "could be extracted"
            )

        return MedicalContext(
            diagnoses=diagnoses,
            symptoms=symptoms,
            procedures=procedures,
            medications=medications,
            clinical_findings=clinical_findings,
            icd10_codes=icd10_codes,
            canonical_specialties=canonical_specialties,
            primary_specialty=primary_specialty,
            extraction_status=extraction_status,
            clarification_required=clarification_required,
            clarification_reason=clarification_reason
        )


if __name__ == "__main__":

    context_1 = MedicalContext(
        diagnoses=[
            "coronary artery disease"
        ],
        symptoms=[
            "chest pain"
        ],
        icd10_codes=[
            "I25"
        ],
        canonical_specialties=[
            "Cardiology"
        ],
        primary_specialty="Cardiology",
        extraction_status="success"
    )

    context_2 = MedicalContext(
        procedures=[
            "CABG"
        ],
        medications=[
            "aspirin"
        ],
        extraction_status="needs_review",
        clarification_required=True,
        clarification_reason=(
            "No diagnosis found in this report"
        )
    )

    aggregator = PatientContextAggregator()

    result = aggregator.aggregate(
        [
            context_1,
            context_2
        ]
    )

    print(
        result.model_dump()
    )