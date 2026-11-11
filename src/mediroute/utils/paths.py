"""Single source of truth for project file-system locations.

Every module should import paths from here instead of computing
``Path(__file__).parents[N]``, so files can move without breaking lookups.

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
TAXONOMY_DIR = DATA_DIR / "medical_taxonomy"
VECTOR_STORE_DIR = DATA_DIR / "vector_store"
GENERATOR_INPUT_DIR = RAW_DATA_DIR / "data_generator"

REFERENCE_DIR = DATA_DIR / "reference"

# The one hospital table both steps read (built by data_generator/build_hospitals_table.py).
HOSPITALS_FILE = PROCESSED_DATA_DIR / "hospitals.csv"
# Verified master it is built from (NABH / JCI / website checks), and the id links to the team sheet.
HOSPITAL_MASTER_FILE = PROCESSED_DATA_DIR / "master-hospital-data.csv"
HOSPITAL_LINKS_FILE = PROCESSED_DATA_DIR / "hospital_id_links.csv"
# Cities, their state and tier, and the search area they belong to (Delhi NCR, Mumbai...).
CITIES_FILE = REFERENCE_DIR / "cities.csv"
# Team 150-hospital sheet: input only (procedures, facilities, sub-specialities, cost band).
TEAM_150_SHEET_FILE = RAW_DATA_DIR / "NewMediRoute_Hospital_Dataset_150.xlsx"
HOSPITAL_DATASET_FILE = TEAM_150_SHEET_FILE  # old name, kept for existing imports

LOG_DIR = Path(os.getenv("MEDIROUTE_LOG_DIR", PROJECT_ROOT / "logs"))
FRONTEND_DIR = PROJECT_ROOT / "frontend"
