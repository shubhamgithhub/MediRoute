from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[4]

VECTOR_STORE_DIR = (
    PROJECT_ROOT
    / "Data"
    / "vector_store"
)

EMBEDDING_DATASET_FILE = (
    VECTOR_STORE_DIR
    / "hospital_embedding_dataset.csv"
)

METADATA_FILE = (
    VECTOR_STORE_DIR
    / "hospital_metadata.json"
)

FAISS_INDEX_FILE = (
    VECTOR_STORE_DIR
    / "hospital_index.faiss"
)

FAISS_MANIFEST_FILE = (
    VECTOR_STORE_DIR
    / "hospital_index_manifest.json"
)

EMBEDDING_MODEL_NAME = (
    "sentence-transformers/"
    "multi-qa-MiniLM-L6-cos-v1"
)

DEFAULT_TOP_K = 10