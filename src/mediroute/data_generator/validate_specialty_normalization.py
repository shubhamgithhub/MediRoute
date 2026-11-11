from pathlib import Path
import pandas as pd


from mediroute.utils.paths import PROJECT_ROOT  # noqa: E402

NORMALIZATION_FILE = (
    PROJECT_ROOT
    / "data"
    / "medical_taxonomy"
    / "specialty_normalization.csv"
)


def validate_normalization():

    df = pd.read_csv(NORMALIZATION_FILE)

    required_columns = [
        "raw_specialty",
        "canonical_specialty",
        "normalization_status",
        "notes",
    ]

    print("\nSTEP 7B — SPECIALTY NORMALIZATION VALIDATION")
    print("=" * 55)

    # 1. Check required columns
    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Missing columns: {missing_columns}"
        )

    print(f"Total specialty rows: {len(df)}")

    # 2. Check empty canonical specialties
    empty_canonical = df[
        df["canonical_specialty"].isna()
        | (
            df["canonical_specialty"]
            .astype(str)
            .str.strip()
            == ""
        )
    ]

    print(
        f"Rows without canonical specialty: "
        f"{len(empty_canonical)}"
    )

    # 3. Check statuses
    # draft_rule = keyword-rule mapping waiting for doctor review
    allowed_statuses = {
        "reviewed",
        "review_needed",
        "draft_rule",
    }

    invalid_status = df[
        ~df["normalization_status"].isin(
            allowed_statuses
        )
    ]

    print(
        f"Rows with invalid status: "
        f"{len(invalid_status)}"
    )

    # 4. A label may map to several specialities (one row each), but never twice to the same one
    duplicates = df[
        df.duplicated(
            subset=["raw_specialty", "canonical_specialty"],
            keep=False
        )
    ]

    print(
        f"Duplicate label -> speciality rows: "
        f"{len(duplicates)}"
    )

    # 4b. Every target is one of Step 1's specialities (specialties.csv) or NONE
    from mediroute.common.specialties import specialty_names

    unknown = sorted(set(df["canonical_specialty"].astype(str)) - set(specialty_names()) - {"NONE"})
    print(f"Targets not in specialties.csv: {unknown or 'none'}")
    if len(invalid_status) or len(duplicates) or unknown:
        raise SystemExit("specialty_normalization.csv has problems (see above)")

    # 5. Show review-needed rows
    review_needed = df[
        df["normalization_status"]
        == "review_needed"
    ]

    print(
        f"Rows requiring review: "
        f"{len(review_needed)}"
    )

    if not review_needed.empty:
        print("\nReview-needed specialties:")

        for _, row in review_needed.iterrows():
            print(
                f"- {row['raw_specialty']} "
                f"-> {row['canonical_specialty']}"
            )

    # 6. Show canonical specialty vocabulary
    canonical_values = sorted(
        df["canonical_specialty"]
        .dropna()
        .astype(str)
        .str.strip()
        .loc[
            lambda x: x != ""
        ]
        .unique()
    )

    print(
        f"\nUnique canonical specialties: "
        f"{len(canonical_values)}"
    )

    print("\nCanonical specialty vocabulary:")

    for specialty in canonical_values:
        print(f"- {specialty}")

    print("\nValidation complete.")


if __name__ == "__main__":
    validate_normalization()