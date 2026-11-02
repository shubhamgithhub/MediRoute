from src.Src.backend.medical_context import MedicalContext
from src.Src.backend.services.patient_context_aggregator import (
    PatientContextAggregator,
)
from src.Src.backend.services.patient_context_validator import (
    PatientContextValidator,
)


def run_tests():

    aggregator = PatientContextAggregator()
    validator = PatientContextValidator()

    print("\nSTEP 9 — PATIENT CONTEXT VALIDATION")
    print("=" * 60)

    passed = 0
    failed = 0

    # -------------------------------------------------
    # TEST 1 — Consistent Cardiology
    # -------------------------------------------------

    contexts = [
        MedicalContext(
            diagnoses=["tachycardia"],
            icd10_codes=["R00.0"],
            canonical_specialties=["Cardiology"],
            primary_specialty="Cardiology",
            extraction_status="success"
        ),

        MedicalContext(
            diagnoses=["hypertension"],
            icd10_codes=["I10"],
            canonical_specialties=["Cardiology"],
            primary_specialty="Cardiology",
            extraction_status="success"
        )
    ]

    aggregated = aggregator.aggregate(
        contexts
    )

    result = validator.validate(
        contexts,
        aggregated
    )

    if (
        result["consistency_status"]
        == "consistent"
        and result["routing_ready"] is True
    ):
        print("T001: PASS — consistent specialty")
        passed += 1
    else:
        print("T001: FAIL")
        failed += 1

    # -------------------------------------------------
    # TEST 2 — Multiple specialty conflict
    # -------------------------------------------------

    contexts = [
        MedicalContext(
            diagnoses=["tachycardia"],
            canonical_specialties=["Cardiology"],
            primary_specialty="Cardiology",
            extraction_status="success"
        ),

        MedicalContext(
            diagnoses=["breast cancer"],
            canonical_specialties=["Oncology"],
            primary_specialty="Oncology",
            extraction_status="success"
        )
    ]

    aggregated = aggregator.aggregate(
        contexts
    )

    result = validator.validate(
        contexts,
        aggregated
    )

    if (
        result["consistency_status"]
        == "conflict"
        and result["routing_ready"] is False
    ):
        print("T002: PASS — specialty conflict")
        passed += 1
    else:
        print("T002: FAIL")
        failed += 1

    # -------------------------------------------------
    # TEST 3 — Partial success
    # -------------------------------------------------

    contexts = [
        MedicalContext(
            diagnoses=["tachycardia"],
            canonical_specialties=["Cardiology"],
            primary_specialty="Cardiology",
            extraction_status="success"
        ),

        MedicalContext(
            extraction_status="needs_review",
            clarification_required=True,
            clarification_reason=(
                "No diagnosis found"
            )
        )
    ]

    aggregated = aggregator.aggregate(
        contexts
    )

    result = validator.validate(
        contexts,
        aggregated
    )

    if (
        result["consistency_status"]
        == "partial"
        and result["routing_ready"] is False
    ):
        print("T003: PASS — partial report set")
        passed += 1
    else:
        print("T003: FAIL")
        failed += 1

    # -------------------------------------------------
    # TEST 4 — No routable specialty
    # -------------------------------------------------

    contexts = [
        MedicalContext(
            symptoms=["dizziness"],
            extraction_status="needs_review",
            clarification_required=True
        ),

        MedicalContext(
            procedures=["ECG"],
            extraction_status="needs_review",
            clarification_required=True
        )
    ]

    aggregated = aggregator.aggregate(
        contexts
    )

    result = validator.validate(
        contexts,
        aggregated
    )

    if (
        result["consistency_status"]
        == "needs_review"
        and result["routing_ready"] is False
    ):
        print("T004: PASS — no routable specialty")
        passed += 1
    else:
        print("T004: FAIL")
        failed += 1

    # -------------------------------------------------
    # FINAL RESULT
    # -------------------------------------------------

    total = passed + failed

    print("\n" + "=" * 60)
    print(f"Total tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    accuracy = (
        passed / total
        if total > 0
        else 0
    )

    print(
        f"Accuracy: {accuracy:.2%}"
    )


if __name__ == "__main__":
    run_tests()