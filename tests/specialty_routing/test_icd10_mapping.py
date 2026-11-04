from pathlib import Path
import pandas as pd

from mediroute.specialty_routing.icd10_mapper import ICD10Mapper


from mediroute.utils.paths import PROJECT_ROOT  # noqa: E402

TEST_FILE = (
    PROJECT_ROOT
    / "data"
    / "medical_taxonomy"
    / "icd10_mapping_test_cases.csv"
)


def run_tests():

    mapper = ICD10Mapper()

    df = pd.read_csv(TEST_FILE)

    total_tests = len(df)
    passed = 0
    failed = 0

    print("\nSTEP 7F — ICD-10 MAPPING VALIDATION")
    print("=" * 55)

    for _, row in df.iterrows():

        test_id = row["test_id"]
        input_type = row["input_type"]
        input_value = row["input_value"]

        expected_code = (
            None
            if pd.isna(row["expected_icd10_code"])
            else str(row["expected_icd10_code"]).strip()
        )

        expected_specialty = (
            None
            if pd.isna(row["expected_specialty"])
            else str(row["expected_specialty"]).strip()
        )

        if input_type == "condition":

            result = mapper.find_by_condition(
                input_value
            )

        elif input_type == "icd10_code":

            result = mapper.find_by_icd10_code(
                input_value
            )

        else:

            print(
                f"{test_id}: FAIL "
                f"(unknown input_type: {input_type})"
            )

            failed += 1
            continue

        actual_matched = result.get(
            "matched",
            False
        )

        actual_code = result.get(
            "icd10_code"
        )

        actual_specialty = result.get(
            "canonical_specialty"
        )

        # Expected no-match case
        if (
            expected_code is None
            and expected_specialty is None
        ):

            if not actual_matched:

                print(
                    f"{test_id}: PASS "
                    f"{input_value} -> no match"
                )

                passed += 1

            else:

                print(
                    f"{test_id}: FAIL "
                    f"expected no match but got "
                    f"{actual_code}, "
                    f"{actual_specialty}"
                )

                failed += 1

            continue

        # Expected matched case
        if (
            actual_matched
            and actual_code == expected_code
            and actual_specialty
            == expected_specialty
        ):

            print(
                f"{test_id}: PASS "
                f"{input_value} -> "
                f"{actual_code} -> "
                f"{actual_specialty}"
            )

            passed += 1

        else:

            print(
                f"{test_id}: FAIL"
            )

            print(
                f"  Expected: "
                f"{expected_code}, "
                f"{expected_specialty}"
            )

            print(
                f"  Actual: "
                f"{actual_code}, "
                f"{actual_specialty}"
            )

            failed += 1

    print("\n" + "=" * 55)

    print(f"Total tests: {total_tests}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    accuracy = (
        passed / total_tests
        if total_tests > 0
        else 0
    )

    print(
        f"Accuracy: "
        f"{accuracy:.2%}"
    )


if __name__ == "__main__":
    run_tests()