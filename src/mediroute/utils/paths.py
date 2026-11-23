"""Single source of truth for project file-system locations.

Every module should import paths from here instead of computing
``Path(__file__).parents[N]``, so files can move without breaking lookups.

Data layout (README section 6):

    data/processed/   the ONLY folder the app reads; every file is either maintained by hand
                      (specialties.csv, specialty_mapping.csv, cities.csv, hospital.schema.csv)
                      or rebuilt from raw/ + interim/ by `python -m mediroute.data_generator.rebuild`
    data/raw/         official sources and team sheets, never edited
    data/interim/     pipeline intermediates (hospital verification outputs, verified master)
    data/evaluation/  gold test sets and benchmark results (not read by the app)

Set ``MEDIROUTE_DATA_DIR`` to point the app at a data folder elsewhere.
"""

import os
from pathlib import Path

# src/mediroute/utils/paths.py -> repo root is three levels above `mediroute/`
PROJECT_ROOT = Path(__file__).resolve().parents[3]

DATA_DIR = Path(os.getenv("MEDIROUTE_DATA_DIR", PROJECT_ROOT / "data"))
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
INTERIM_DATA_DIR = DATA_DIR / "interim"
EVALUATION_DIR = DATA_DIR / "evaluation"
# user accounts and saved history (SQLite; never committed): docs/design/user_history.md
APP_DB_FILE = Path(os.getenv("MEDIROUTE_APP_DB", DATA_DIR / "app" / "mediroute.db"))
VECTOR_STORE_DIR = PROCESSED_DATA_DIR / "vector_store"
GENERATOR_INPUT_DIR = RAW_DATA_DIR / "data_generator"

# --- maintained by hand (reviewed) -------------------------------------------------------------
# The master list: the 26 specialities both steps use, with descriptions and routing boundaries.
SPECIALTIES_FILE = PROCESSED_DATA_DIR / "specialties.csv"
# Every "X -> speciality" rule: CCSR categories, CGHS procedures, lay terms, hospital labels.
SPECIALTY_MAPPING_FILE = PROCESSED_DATA_DIR / "specialty_mapping.csv"
# Cities, their state and tier, and the search area they belong to (Delhi NCR, Mumbai...).
CITIES_FILE = PROCESSED_DATA_DIR / "cities.csv"
# Step 1 multi-area check: symptom tag -> body area, and neighbour tags that count as one area.
BODY_AREA_TAGS_FILE = PROCESSED_DATA_DIR / "body_area_tags.csv"
BODY_AREA_NEIGHBOURS_FILE = PROCESSED_DATA_DIR / "body_area_neighbours.csv"
# Step 2: related speciality to show in the patient's area when no hospital there has the suggested one.
SPECIALTY_FALLBACKS_FILE = PROCESSED_DATA_DIR / "specialty_fallbacks.csv"
HOSPITAL_SCHEMA_FILE = PROCESSED_DATA_DIR / "hospital.schema.csv"

# --- rebuilt (python -m mediroute.data_generator.rebuild) ---------------------------------------
# The one hospital table both steps read (built by data_generator/build_hospitals_table.py).
HOSPITALS_FILE = PROCESSED_DATA_DIR / "hospitals.csv"
# Step 1 search terms (built by specialty_routing/step1/lookup.py).
STEP1_LOOKUP_FILE = PROCESSED_DATA_DIR / "step1_lookup.csv"

# --- pipeline inputs ----------------------------------------------------------------------------
# Verified master (NABH / JCI / website checks, written by merge_master.py) and the reviewed id
# links to the team sheet: inputs of hospitals.csv.
HOSPITAL_MASTER_FILE = INTERIM_DATA_DIR / "master-hospital-data.csv"
HOSPITAL_LINKS_FILE = INTERIM_DATA_DIR / "hospital_id_links.csv"
# NABH status checked by a person (directory record or the hospital's own statement); replaces the
# master's automatic NABH match for the listed hospitals. Applied by build_hospitals_table.py.
NABH_MANUAL_FILE = INTERIM_DATA_DIR / "nabh_manual_verification.csv"
# Team 150-hospital sheet: input only (procedures, facilities, sub-specialities, cost band).
TEAM_150_SHEET_FILE = RAW_DATA_DIR / "NewMediRoute_Hospital_Dataset_150.xlsx"
HOSPITAL_DATASET_FILE = TEAM_150_SHEET_FILE  # old name, kept for existing imports
# Official medical sources for the Step 1 lookup.
ICD_ORDER_FILE = RAW_DATA_DIR / "icd10cm_2026" / "extracted" / "icd10cm-order-2026.txt"
CCSR_FILE = RAW_DATA_DIR / "ccsr_v2023_1" / "DXCCSR-Reference-File-v2023-1.xlsx"
CGHS_WORKBOOK = GENERATOR_INPUT_DIR / "Hosp_Data_Final.xlsx"

LOG_DIR = Path(os.getenv("MEDIROUTE_LOG_DIR", PROJECT_ROOT / "logs"))
FRONTEND_DIR = PROJECT_ROOT / "frontend"
