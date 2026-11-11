from pathlib import Path


from mediroute.utils.paths import VECTOR_STORE_DIR  # noqa: E402  (data/processed/vector_store)

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