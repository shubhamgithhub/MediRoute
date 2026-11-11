from pathlib import Path
import pandas as pd


from mediroute.utils.paths import PROJECT_ROOT  # noqa: E402

SOURCE_FILE = PROJECT_ROOT / "data" / "raw" / "SampleData.csv"
OUTPUT_FILE = PROJECT_ROOT / "data" / "processed" / "hospitals_master.csv"


def create_master_dataset():

    # Existing file is tab-separated
    df = pd.read_csv(SOURCE_FILE, sep="\t")

    # Preserve existing data
    master_df = df.copy()

    # New fields required after TA feedback
    master_df["state"] = ""
    master_df["accreditation_verified"] = False
    master_df["accreditation_source"] = ""

    master_df["hospital_type"] = ""

    master_df["specialty_verified"] = False
    master_df["specialty_source"] = ""

    master_df["key_services"] = ""
    master_df["facilities"] = ""

    master_df["international_patient_support"] = "Unknown"

    master_df["cost_type"] = "Reference proxy"
    master_df["cost_source"] = "CGHS"

    master_df["data_source_url"] = ""
    master_df["last_verified_date"] = ""

    master_df["is_synthetic"] = True

    master_df["notes"] = ""

    master_df.to_csv(
        OUTPUT_FILE,
        index=False
    )

    print("MediRoute master hospital dataset created.")
    print(f"Rows: {len(master_df)}")
    print(f"Saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    create_master_dataset()