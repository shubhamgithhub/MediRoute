from src.Src.backend.medical_context import MedicalContext
from src.Src.backend.services.icd10_mapper import ICD10Mapper


class MedicalContextExtractor:

    def __init__(self):
        self.icd10_mapper = ICD10Mapper()

    def extract(self, text: str) -> MedicalContext:

        if not text or not text.strip():
            return MedicalContext(
                extraction_status="failed",
                clarification_required=True,
                clarification_reason="No readable medical text available"
            )

        text_lower = text.lower()

        diagnoses = []
        symptoms = []
        procedures = []
        medications = []
        clinical_findings = []

        # -------------------------------------------------
        # Diagnosis rules
        # -------------------------------------------------

        if "myocardial infarction" in text_lower:
            diagnoses.append(
                "myocardial infarction"
            )

        if "coronary artery disease" in text_lower:
            diagnoses.append(
                "coronary artery disease"
            )

        if "heart failure" in text_lower:
            diagnoses.append(
                "heart failure"
            )

        if "breast cancer" in text_lower:
            diagnoses.append(
                "breast cancer"
            )

        if "type 2 diabetes" in text_lower:
            diagnoses.append(
                "type 2 diabetes"
            )

        if "knee osteoarthritis" in text_lower:
            diagnoses.append(
                "knee osteoarthritis"
            )

        if "ischemic stroke" in text_lower:
            diagnoses.append(
                "ischemic stroke"
            )

        if "arrhythmia" in text_lower:
            diagnoses.append(
                "arrhythmia"
            )

        if "bradycardia" in text_lower:
            diagnoses.append(
                "bradycardia"
            )

        if "tachycardia" in text_lower:
            diagnoses.append(
                "tachycardia"
            )

        if "hypertension" in text_lower:
            diagnoses.append(
                "hypertension"
            )

        # -------------------------------------------------
        # Symptom rules
        # -------------------------------------------------

        if "chest pain" in text_lower:
            symptoms.append(
                "chest pain"
            )

        if "palpitations" in text_lower:
            symptoms.append(
                "palpitations"
            )

        if "shortness of breath" in text_lower:
            symptoms.append(
                "shortness of breath"
            )

        if "dizziness" in text_lower:
            symptoms.append(
                "dizziness"
            )

        if "fatigue" in text_lower:
            symptoms.append(
                "fatigue"
            )

        if "syncope" in text_lower:
            symptoms.append(
                "syncope"
            )

        # -------------------------------------------------
        # Procedure rules
        # -------------------------------------------------

        if "cabg" in text_lower:
            procedures.append(
                "CABG"
            )

        if "angioplasty" in text_lower:
            procedures.append(
                "angioplasty"
            )

        if "ecg" in text_lower:
            procedures.append(
                "ECG"
            )

        if "echocardiogram" in text_lower:
            procedures.append(
                "Echocardiogram"
            )

        if "angiography" in text_lower:
            procedures.append(
                "Angiography"
            )

        # -------------------------------------------------
        # Medication rules
        # -------------------------------------------------

        if "aspirin" in text_lower:
            medications.append(
                "aspirin"
            )

        if "atorvastatin" in text_lower:
            medications.append(
                "atorvastatin"
            )

        # -------------------------------------------------
        # Clinical finding rules
        # -------------------------------------------------

        if "sinus bradycardia" in text_lower:
            clinical_findings.append(
                "sinus bradycardia"
            )

        if "sinus tachycardia" in text_lower:
            clinical_findings.append(
                "sinus tachycardia"
            )

        if "premature ventricular contraction" in text_lower:
            clinical_findings.append(
                "premature ventricular contraction"
            )

        if "pvc" in text_lower:
            clinical_findings.append(
                "PVC"
            )

        if "st depression" in text_lower:
            clinical_findings.append(
                "ST depression"
            )

        if "st elevation" in text_lower:
            clinical_findings.append(
                "ST elevation"
            )

        if "abnormal ecg" in text_lower:
            clinical_findings.append(
                "abnormal ECG"
            )

        if "reduced ejection fraction" in text_lower:
            clinical_findings.append(
                "reduced ejection fraction"
            )

        # -------------------------------------------------
        # Remove duplicate values
        # -------------------------------------------------

        diagnoses = list(dict.fromkeys(diagnoses))
        symptoms = list(dict.fromkeys(symptoms))
        procedures = list(dict.fromkeys(procedures))
        medications = list(dict.fromkeys(medications))
        clinical_findings = list(
            dict.fromkeys(clinical_findings)
        )

        # -------------------------------------------------
        # Check whether useful medical information exists
        # -------------------------------------------------

        extraction_found = any(
            [
                diagnoses,
                symptoms,
                procedures,
                medications,
                clinical_findings,
            ]
        )

        if not extraction_found:
            return MedicalContext(
                extraction_status="needs_review",
                clarification_required=True,
                clarification_reason=(
                    "Medical text was readable, "
                    "but no supported medical concepts "
                    "were identified"
                )
            )

        # -------------------------------------------------
        # ICD-10 and specialty mapping
        # -------------------------------------------------

        icd10_codes = []
        canonical_specialties = []
        unmapped_diagnoses = []

        for diagnosis in diagnoses:

            mapping = (
                self.icd10_mapper
                .find_by_condition(
                    diagnosis
                )
            )

            if mapping.get("matched"):

                icd10_code = mapping.get(
                    "icd10_code"
                )

                specialty = mapping.get(
                    "canonical_specialty"
                )

                if (
                    icd10_code
                    and icd10_code
                    not in icd10_codes
                ):
                    icd10_codes.append(
                        icd10_code
                    )

                if (
                    specialty
                    and specialty
                    not in canonical_specialties
                ):
                    canonical_specialties.append(
                        specialty
                    )

            else:
                unmapped_diagnoses.append(
                    diagnosis
                )

        # -------------------------------------------------
        # Select primary specialty
        # -------------------------------------------------

        primary_specialty = (
            canonical_specialties[0]
            if canonical_specialties
            else None
        )

        # -------------------------------------------------
        # Validation / clarification logic
        # -------------------------------------------------

        # Case 1:
        # A diagnosis was found, but none of the diagnoses
        # could be mapped to ICD-10 / specialty.
        if (
            diagnoses
            and not canonical_specialties
        ):

            return MedicalContext(
                diagnoses=diagnoses,
                symptoms=symptoms,
                procedures=procedures,
                medications=medications,
                clinical_findings=clinical_findings,
                icd10_codes=icd10_codes,
                canonical_specialties=canonical_specialties,
                primary_specialty=primary_specialty,
                extraction_status="needs_review",
                clarification_required=True,
                clarification_reason=(
                    "Diagnosis was extracted, "
                    "but no ICD-10 specialty mapping "
                    "was found"
                )
            )

        # Case 2:
        # Some diagnoses mapped, but others did not.
        if unmapped_diagnoses:

            return MedicalContext(
                diagnoses=diagnoses,
                symptoms=symptoms,
                procedures=procedures,
                medications=medications,
                clinical_findings=clinical_findings,
                icd10_codes=icd10_codes,
                canonical_specialties=canonical_specialties,
                primary_specialty=primary_specialty,
                extraction_status="needs_review",
                clarification_required=True,
                clarification_reason=(
                    "Some diagnoses were mapped, "
                    "but others still require review: "
                    + ", ".join(unmapped_diagnoses)
                )
            )

        # Case 3:
        # Medical concepts were found, but no diagnosis
        # was present. This is readable medical information,
        # but it is not yet enough for confident routing.
        if (
            not diagnoses
            and (
                symptoms
                or procedures
                or clinical_findings
                or medications
            )
        ):

            return MedicalContext(
                diagnoses=diagnoses,
                symptoms=symptoms,
                procedures=procedures,
                medications=medications,
                clinical_findings=clinical_findings,
                icd10_codes=icd10_codes,
                canonical_specialties=canonical_specialties,
                primary_specialty=primary_specialty,
                extraction_status="needs_review",
                clarification_required=True,
                clarification_reason=(
                    "Medical concepts were identified, "
                    "but no supported diagnosis was found "
                    "for specialty routing"
                )
            )

        # -------------------------------------------------
        # Successful extraction
        # -------------------------------------------------

        return MedicalContext(
            diagnoses=diagnoses,
            symptoms=symptoms,
            procedures=procedures,
            medications=medications,
            clinical_findings=clinical_findings,
            icd10_codes=icd10_codes,
            canonical_specialties=canonical_specialties,
            primary_specialty=primary_specialty,
            extraction_status="success",
            clarification_required=False,
            clarification_reason=None
        )


if __name__ == "__main__":

    sample_text = """
    Patient reports chest pain and palpitations.
    ECG shows sinus tachycardia.
    History of coronary artery disease.
    Patient is taking aspirin.
    """

    extractor = MedicalContextExtractor()

    result = extractor.extract(
        sample_text
    )

    print(
        result.model_dump()
    )