"""Build the Step 2 search dataset (hospital_embedding_dataset.csv + hospital_metadata.json) from
data/processed/hospitals.csv, the one hospital table. Then run build_faiss_index.

    python -m mediroute.data_generator.build_hospitals_table
    python -m mediroute.data_generator.build_hospital_embedding_dataset
    python -m mediroute.data_generator.build_faiss_index
"""
from pathlib import Path
import json
import pandas as pd

from mediroute.hospital_recommendation.retrieval.hospital_search_text_builder import (
    HospitalSearchTextBuilder,
)


# ---------------------------------------------------------
# Project paths
# ---------------------------------------------------------

from mediroute.utils.paths import PROJECT_ROOT  # noqa: E402

from mediroute.utils.paths import HOSPITALS_FILE as HOSPITAL_FILE  # noqa: E402

from mediroute.utils.paths import VECTOR_STORE_DIR as OUTPUT_DIR  # noqa: E402  (data/processed/vector_store)

OUTPUT_CSV = (
    OUTPUT_DIR
    / "hospital_embedding_dataset.csv"
)

OUTPUT_JSON = (
    OUTPUT_DIR
    / "hospital_metadata.json"
)


# ---------------------------------------------------------
# Helper functions
# ---------------------------------------------------------

def clean_value(value):
    """
    Convert NaN / empty spreadsheet values
    into clean Python strings.
    """

    if pd.isna(value):
        return ""

    return str(value).strip()


def get_first_available_value(
    hospital: dict,
    possible_columns: list[str]
):
    """
    Return the first available non-empty value
    from a list of possible column names.

    This helps avoid breaking the code if the
    hospital-name column uses a slightly different
    heading in the Excel file.
    """

    for column in possible_columns:

        if column in hospital:

            value = clean_value(
                hospital.get(column)
            )

            if value:
                return value

    return ""


# ---------------------------------------------------------
# Main builder
# ---------------------------------------------------------

def build_hospital_embedding_dataset():

    print()
    print(
        "STEP 10 — BUILD HOSPITAL "
        "EMBEDDING DATASET"
    )
    print("=" * 60)

    # -----------------------------------------------------
    # Validate source file
    # -----------------------------------------------------

    if not HOSPITAL_FILE.exists():

        raise FileNotFoundError(
            f"Hospital dataset not found: "
            f"{HOSPITAL_FILE}"
        )

    print(
        f"Loading hospital dataset:\n"
        f"{HOSPITAL_FILE}"
    )

    # -----------------------------------------------------
    # Load Hospitals_150
    # -----------------------------------------------------

    df = pd.read_csv(
        HOSPITAL_FILE,
        dtype=str,
        keep_default_na=False,
    )

    print(
        f"\nHospital rows loaded: "
        f"{len(df)}"
    )

    # -----------------------------------------------------
    # Required fields
    # -----------------------------------------------------

    required_columns = [
        "hospital_id",
        "verified_specialties",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:

        raise ValueError(
            "Missing required hospital columns: "
            f"{missing_columns}\n\n"
            f"Available columns:\n"
            f"{list(df.columns)}"
        )

    # -----------------------------------------------------
    # Build searchable text
    # -----------------------------------------------------

    text_builder = (
        HospitalSearchTextBuilder()
    )

    output_rows = []
    metadata_rows = []

    for index, row in df.iterrows():

        hospital = row.to_dict()

        hospital_id = clean_value(
            hospital.get(
                "hospital_id"
            )
        )

        hospital_name = (
            get_first_available_value(
                hospital,
                [
                    "hospital_name",
                    "hospital name",
                    "name",
                    "Hospital Name",
                ]
            )
        )

        search_text = (
            text_builder.build_search_text(
                hospital
            )
        )

        # ---------------------------------------------
        # Skip unusable rows
        # ---------------------------------------------

        if not hospital_id:

            print(
                f"WARNING: Row {index + 2} "
                f"has no hospital_id. Skipping."
            )

            continue

        if not search_text:

            print(
                f"WARNING: {hospital_id} "
                f"has no searchable text. "
                f"Skipping."
            )

            continue

        # ---------------------------------------------
        # Embedding dataset row
        # ---------------------------------------------

        output_rows.append(
            {
                "hospital_id":
                    hospital_id,

                "hospital_name":
                    hospital_name,

                "hospital_search_text":
                    search_text,
            }
        )

        # ---------------------------------------------
        # Metadata used after FAISS retrieval
        # ---------------------------------------------

        metadata_rows.append(
            {
                "vector_position":
                    len(metadata_rows),

                "hospital_id":
                    hospital_id,

                "hospital_name":
                    hospital_name,

                "city":
                    clean_value(
                        hospital.get(
                            "city"
                        )
                    ),

                "state":
                    clean_value(
                        hospital.get(
                            "state"
                        )
                    ),

                "verified_specialties":
                    clean_value(
                        hospital.get(
                            "verified_specialties"
                        )
                    ),

                "team_claimed_specialties":
                    clean_value(
                        hospital.get(
                            "team_claimed_specialties"
                        )
                    ),

                "subspecialties":
                    clean_value(
                        hospital.get(
                            "subspecialties"
                        )
                    ),

                "procedures":
                    clean_value(
                        hospital.get(
                            "procedures"
                        )
                    ),

                "facilities":
                    clean_value(
                        hospital.get(
                            "facilities"
                        )
                    ),

                "languages":
                    clean_value(
                        hospital.get(
                            "languages"
                        )
                    ),

                "detail_source":
                    clean_value(
                        hospital.get(
                            "detail_source"
                        )
                    ),

                "international_patient_service":
                    clean_value(
                        hospital.get(
                            "international_patient_service"
                        )
                    ),

                "url_Internantional_patients":
                    clean_value(
                        hospital.get(
                            "url_Internantional_patients"
                        )
                    ),

                "nabh_status":
                    clean_value(
                        hospital.get(
                            "nabh_status"
                        )
                    ),

                "jci_status":
                    clean_value(
                        hospital.get(
                            "jci_status"
                        )
                    ),

                "verification_status":
                    clean_value(
                        hospital.get(
                            "verification_status"
                        )
                    ),

                "evidence_quality_score":
                    clean_value(
                        hospital.get(
                            "evidence_quality_score"
                        )
                    ),

                "cost_band_inr":
                    clean_value(
                        hospital.get(
                            "cost_band_inr"
                        )
                    ),

                "official_source_url":
                    clean_value(
                        hospital.get(
                            "official_source_url"
                        )
                    ),

                "record_origin":
                    clean_value(
                        hospital.get(
                            "record_origin"
                        )
                    ),

                "team150_id":
                    clean_value(
                        hospital.get(
                            "team150_id"
                        )
                    ),

                "hospital_search_text":
                    search_text,
            }
        )

    # -----------------------------------------------------
    # Save output directory
    # -----------------------------------------------------

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # -----------------------------------------------------
    # Save embedding CSV
    # -----------------------------------------------------

    output_df = pd.DataFrame(
        output_rows
    )

    output_df.to_csv(
        OUTPUT_CSV,
        index=False
    )

    # -----------------------------------------------------
    # Save metadata JSON
    # -----------------------------------------------------

    with open(
        OUTPUT_JSON,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            metadata_rows,
            file,
            indent=2,
            ensure_ascii=False
        )

    # -----------------------------------------------------
    # Validation summary
    # -----------------------------------------------------

    print()
    print(
        "Embedding dataset created."
    )

    print(
        f"Source hospital rows: "
        f"{len(df)}"
    )

    print(
        f"Embedding rows created: "
        f"{len(output_df)}"
    )

    print(
        f"Metadata rows created: "
        f"{len(metadata_rows)}"
    )

    print()
    print(
        f"CSV saved to:\n"
        f"{OUTPUT_CSV}"
    )

    print()
    print(
        f"Metadata saved to:\n"
        f"{OUTPUT_JSON}"
    )

    # -----------------------------------------------------
    # Critical consistency check
    # -----------------------------------------------------

    if len(output_df) != len(
        metadata_rows
    ):

        raise ValueError(
            "Embedding rows and metadata "
            "rows do not match."
        )

    if len(output_df) != len(df):

        print()
        print(
            "WARNING:"
        )

        print(
            "Not every hospital row produced "
            "an embedding record."
        )

        print(
            "Review the warnings above "
            "before building FAISS."
        )

    else:

        print()
        print(
            "SUCCESS: Every hospital row "
            "produced an embedding record."
        )


if __name__ == "__main__":

    build_hospital_embedding_dataset()