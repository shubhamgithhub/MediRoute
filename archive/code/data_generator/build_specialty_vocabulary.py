from pathlib import Path
import re
import pandas as pd


# Find MediRoute project root
from mediroute.utils.paths import PROJECT_ROOT  # noqa: E402

HOSPITAL_FILE = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "NewMediRoute_Hospital_Dataset_150.xlsx"
)

OUTPUT_DIR = PROJECT_ROOT / "data" / "medical_taxonomy"

OUTPUT_FILE = OUTPUT_DIR / "specialty_vocabulary.csv"

SHEET_NAME = "Hospitals_150"


def split_specialties(value):
    """
    Convert a hospital specialty cell into individual specialty names.

    Supports common separators such as:
    comma, semicolon and pipe.
    """

    if pd.isna(value):
        return []

    value = str(value).strip()

    if not value:
        return []

    specialties = re.split(r"[;,|]", value)

    return [
        specialty.strip()
        for specialty in specialties
        if specialty.strip()
    ]


def build_specialty_vocabulary():

    print(f"Loading hospital dataset:")
    print(HOSPITAL_FILE)

    df = pd.read_excel(
        HOSPITAL_FILE,
        sheet_name=SHEET_NAME
    )

    required_column = "verified_specialties"

    if required_column not in df.columns:
        raise ValueError(
            f"Column '{required_column}' not found.\n"
            f"Available columns: {list(df.columns)}"
        )

    all_specialties = []

    for value in df[required_column]:
        all_specialties.extend(split_specialties(value))

    # Remove duplicates while preserving normalized comparison
    specialty_lookup = {}

    for specialty in all_specialties:

        normalized = specialty.casefold()

        if normalized not in specialty_lookup:
            specialty_lookup[normalized] = specialty

    specialties = sorted(
        specialty_lookup.values(),
        key=str.casefold
    )

    output_df = pd.DataFrame(
        {
            "canonical_specialty": specialties
        }
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    output_df.to_csv(
        OUTPUT_FILE,
        index=False
    )

    print()
    print("Specialty vocabulary created successfully.")
    print(f"Unique specialties: {len(output_df)}")
    print(f"Saved to: {OUTPUT_FILE}")

    print()
    print("Canonical specialties:")

    for specialty in specialties:
        print(f"- {specialty}")


if __name__ == "__main__":
    build_specialty_vocabulary()