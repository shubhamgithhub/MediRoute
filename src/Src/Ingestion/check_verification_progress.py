import csv
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
VERIFICATION_FILE = PROJECT_ROOT / "Data" / "hospital_verification.csv"
VERIFICATION_STATUSES = (
    "Not Started",
    "Partially Verified",
    "Verified",
    "Needs Review",
)


def check_verification_progress():
    with VERIFICATION_FILE.open(encoding="utf-8", newline="") as verification_file:
        hospitals = list(csv.DictReader(verification_file))

    status_counts = {
        status: sum(
            hospital.get("verification_status", "") == status
            for hospital in hospitals
        )
        for status in VERIFICATION_STATUSES
    }

    print("MediRoute Hospital Verification Progress")
    print()
    print(f"Total hospitals: {len(hospitals)}")
    print(f"Verified: {status_counts['Verified']}")
    print(f"Partially Verified: {status_counts['Partially Verified']}")
    print(f"Needs Review: {status_counts['Needs Review']}")
    print(f"Not Started: {status_counts['Not Started']}")
    print()
    print("Verified hospitals:")
    for hospital in hospitals:
        if hospital.get("verification_status", "") == "Verified":
            print(f"- {hospital['name']}")


if __name__ == "__main__":
    check_verification_progress()
