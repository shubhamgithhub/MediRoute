from pathlib import Path
import pandas as pd

from mediroute.backend.services.medical_context_extractor import (
    MedicalContextExtractor,
)


from mediroute.utils.paths import PROJECT_ROOT  # noqa: E402

TEST_FILE = (
    PROJECT_ROOT
    / "data"
    / "medical_taxonomy"
    / "medical_context_test_cases.csv"
)


def clean_expected(value):
    if pd.isna(value):
        return None

    value = str(value).strip()

    return value if value else None


def run_tests():

    extractor = MedicalContextExtractor()

    df = pd.read_csv(TEST_FILE)

    total_tests = len(df)
    passed = 0
    failed = 0

    print("\nSTEP 9A — MEDICAL CONTEXT EXTRACTION VALIDATION")
    print("=" * 60)

    for _, row in df.iterrows():

        test_id = row["test_id"]
        input_text = clean_expected(row["input_text"]) or ""

        expected_diagnosis = clean_expected(
            row["expected_diagnosis"]
        )

        expected_specialty = clean_expected(
            row["expected_specialty"]
        )

        expected_status = clean_expected(
            row["expected_status"]
        )

        result = extractor.extract(
            input_text
        )

        actual_diagnoses = result.diagnoses
        actual_specialty = result.primary_specialty
        actual_status = result.extraction_status

        diagnosis_ok = True

        if expected_diagnosis:
            diagnosis_ok = (
                expected_diagnosis
                in actual_diagnoses
            )
        else:
            diagnosis_ok = (
                len(actual_diagnoses) == 0
            )

        specialty_ok = (
            actual_specialty
            == expected_specialty
        )

        status_ok = (
            actual_status
            == expected_status
        )

        if (
            diagnosis_ok
            and specialty_ok
            and status_ok
        ):

            print(
                f"{test_id}: PASS"
            )

            passed += 1

        else:

            print(
                f"{test_id}: FAIL"
            )

            print(
                f"  Input: {input_text}"
            )

            print(
                f"  Expected diagnosis: "
                f"{expected_diagnosis}"
            )

            print(
                f"  Actual diagnoses: "
                f"{actual_diagnoses}"
            )

            print(
                f"  Expected specialty: "
                f"{expected_specialty}"
            )

            print(
                f"  Actual specialty: "
                f"{actual_specialty}"
            )

            print(
                f"  Expected status: "
                f"{expected_status}"
            )

            print(
                f"  Actual status: "
                f"{actual_status}"
            )

            failed += 1

    print("\n" + "=" * 60)

    print(
        f"Total tests: {total_tests}"
    )

    print(
        f"Passed: {passed}"
    )

    print(
        f"Failed: {failed}"
    )

    accuracy = (
        passed / total_tests
        if total_tests > 0
        else 0
    )

    print(
        f"Accuracy: {accuracy:.2%}"
    )


if __name__ == "__main__":
    run_tests()