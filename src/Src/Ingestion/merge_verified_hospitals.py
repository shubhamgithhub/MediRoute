from pathlib import Path
import shutil
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]

MASTER_FILE = PROJECT_ROOT / "Data" / "hospitals_master.csv"
VERIFICATION_FILE = PROJECT_ROOT / "Data" / "hospital_verification.csv"
BACKUP_FILE = PROJECT_ROOT / "Data" / "hospitals_master_backup.csv"


def to_bool(value):
    return str(value).strip().casefold() in {
        "true",
        "1",
        "yes"
    }


def merge_verified_hospitals():
    # Create backup first
    shutil.copy2(
        MASTER_FILE,
        BACKUP_FILE
    )

    print("Backup created:")
    print(BACKUP_FILE)

    master_df = pd.read_csv(MASTER_FILE)
    verification_df = pd.read_csv(VERIFICATION_FILE)

    updated_count = 0

    for _, verification_row in verification_df.iterrows():

        hospital_id = str(
            verification_row.get("hospital_id", "")
        ).strip()

        verification_status = str(
            verification_row.get(
                "verification_status",
                ""
            )
        ).strip()

        # Only merge hospitals explicitly marked Verified
        if verification_status != "Verified":
            continue

        matching_rows = (
            master_df["hospital_id"]
            .astype(str)
            .str.strip()
            == hospital_id
        )

        if not matching_rows.any():
            print(
                f"Hospital not found in master dataset: "
                f"{hospital_id}"
            )
            continue

        accreditation_verified = to_bool(
            verification_row.get(
                "accreditation_verified",
                False
            )
        )

        specialty_verified = to_bool(
            verification_row.get(
                "specialty_verified",
                False
            )
        )

        # Accreditation verification
        master_df.loc[
            matching_rows,
            "accreditation_verified"
        ] = accreditation_verified

        if accreditation_verified:
            master_df.loc[
                matching_rows,
                "accreditation_source"
            ] = verification_row.get(
                "accreditation_source",
                ""
            )

        # Specialty verification
        master_df.loc[
            matching_rows,
            "specialty_verified"
        ] = specialty_verified

        if specialty_verified:
            master_df.loc[
                matching_rows,
                "specialty_source"
            ] = verification_row.get(
                "specialty_source",
                ""
            )

        # Hospital source
        hospital_source = verification_row.get(
            "hospital_source",
            ""
        )

        if pd.notna(hospital_source):
            master_df.loc[
                matching_rows,
                "data_source_url"
            ] = hospital_source

        # Verification date
        last_verified_date = verification_row.get(
            "last_verified_date",
            ""
        )

        if pd.notna(last_verified_date):
            master_df.loc[
                matching_rows,
                "last_verified_date"
            ] = last_verified_date

        # Notes
        verification_notes = verification_row.get(
            "verification_notes",
            ""
        )

        if pd.notna(verification_notes):
            master_df.loc[
                matching_rows,
                "notes"
            ] = verification_notes

        updated_count += 1

        print(
            f"Updated verified hospital: "
            f"{hospital_id}"
        )

    master_df.to_csv(
        MASTER_FILE,
        index=False
    )

    print()
    print("Verification merge complete.")
    print(f"Hospitals updated: {updated_count}")


if __name__ == "__main__":
    merge_verified_hospitals()