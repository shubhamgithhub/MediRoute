from pathlib import Path
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]

MASTER_FILE = PROJECT_ROOT / "Data" / "hospitals_master.csv"
OUTPUT_FILE = PROJECT_ROOT / "Data" / "hospital_verification.csv"


def create_verification_sheet():

    df = pd.read_csv(MASTER_FILE)

    verification_df = df[
        [
            "hospital_id",
            "name",
            "city",
            "accreditation",
            "key_specialties"
        ]
    ].copy()

    verification_df["accreditation_verified"] = False
    verification_df["accreditation_source"] = ""

    verification_df["specialty_verified"] = False
    verification_df["specialty_source"] = ""

    verification_df["hospital_source"] = ""

    verification_df["last_verified_date"] = ""

    verification_df["verification_status"] = "Not Started"

    verification_df["verification_notes"] = ""

    verification_df.to_csv(
        OUTPUT_FILE,
        index=False
    )

    print("Hospital verification sheet created.")
    print(f"Rows: {len(verification_df)}")
    print(f"Saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    create_verification_sheet()