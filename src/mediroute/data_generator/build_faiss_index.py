import json
from datetime import datetime, timezone

import faiss
import numpy as np
import pandas as pd

from sentence_transformers import SentenceTransformer

from mediroute.hospital_recommendation.retrieval.retrieval_config import (
    EMBEDDING_DATASET_FILE,
    METADATA_FILE,
    FAISS_INDEX_FILE,
    FAISS_MANIFEST_FILE,
    VECTOR_STORE_DIR,
    EMBEDDING_MODEL_NAME,
)


def build_faiss_index():

    print()
    print("STEP 10E — BUILD FAISS INDEX")
    print("=" * 60)

    # -------------------------------------------------
    # Validate required input files
    # -------------------------------------------------

    if not EMBEDDING_DATASET_FILE.exists():
        raise FileNotFoundError(
            f"Embedding dataset not found: "
            f"{EMBEDDING_DATASET_FILE}"
        )

    if not METADATA_FILE.exists():
        raise FileNotFoundError(
            f"Hospital metadata not found: "
            f"{METADATA_FILE}"
        )

    # -------------------------------------------------
    # Load embedding-ready hospital dataset
    # -------------------------------------------------

    df = pd.read_csv(
        EMBEDDING_DATASET_FILE
    )

    required_columns = [
        "hospital_id",
        "hospital_name",
        "hospital_search_text",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Missing required columns: "
            f"{missing_columns}"
        )

    if df.empty:
        raise ValueError(
            "Hospital embedding dataset is empty"
        )

    # -------------------------------------------------
    # Load hospital metadata
    # -------------------------------------------------

    with open(
        METADATA_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        metadata = json.load(
            file
        )

    if len(metadata) != len(df):
        raise ValueError(
            "Metadata row count does not match "
            "embedding dataset row count"
        )

    print(
        f"Hospital documents loaded: "
        f"{len(df)}"
    )

    print(
        f"Embedding model: "
        f"{EMBEDDING_MODEL_NAME}"
    )

    # -------------------------------------------------
    # Load sentence embedding model
    # -------------------------------------------------

    model = SentenceTransformer(
        EMBEDDING_MODEL_NAME
    )

    # -------------------------------------------------
    # Prepare hospital documents
    # -------------------------------------------------

    documents = (
        df["hospital_search_text"]
        .fillna("")
        .astype(str)
        .tolist()
    )

    empty_documents = [
        index
        for index, text in enumerate(documents)
        if not text.strip()
    ]

    if empty_documents:
        raise ValueError(
            "Some hospital search texts are empty. "
            f"Positions: {empty_documents}"
        )

    # -------------------------------------------------
    # Generate embeddings
    #
    # normalize_embeddings=True gives unit-length
    # vectors so IndexFlatIP behaves like cosine
    # similarity.
    # -------------------------------------------------

    embeddings = model.encode_document(
        documents,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True,
    )

    embeddings = np.asarray(
        embeddings,
        dtype="float32"
    )

    # -------------------------------------------------
    # Validate embedding matrix
    # -------------------------------------------------

    if embeddings.ndim != 2:
        raise ValueError(
            "Unexpected embedding matrix shape"
        )

    vector_count = embeddings.shape[0]
    vector_dimension = embeddings.shape[1]

    if vector_count != len(df):
        raise ValueError(
            "Embedding count does not match "
            "hospital count"
        )

    print()
    print(
        f"Embedding shape: "
        f"{embeddings.shape}"
    )

    # -------------------------------------------------
    # Build exact FAISS index
    # -------------------------------------------------

    index = faiss.IndexFlatIP(
        vector_dimension
    )

    index.add(
        embeddings
    )

    if index.ntotal != vector_count:
        raise ValueError(
            "FAISS vector count does not match "
            "embedding count"
        )

    # -------------------------------------------------
    # Ensure vector store directory exists
    # -------------------------------------------------

    VECTOR_STORE_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # -------------------------------------------------
    # Save FAISS index
    # -------------------------------------------------

    faiss.write_index(
        index,
        str(FAISS_INDEX_FILE)
    )

    # -------------------------------------------------
    # Save build manifest
    #
    # This records exactly how the index was built.
    # -------------------------------------------------

    manifest = {
        "embedding_model":
            EMBEDDING_MODEL_NAME,

        "vector_count":
            int(vector_count),

        "vector_dimension":
            int(vector_dimension),

        "faiss_index_type":
            "IndexFlatIP",

        "similarity":
            "cosine_via_normalized_inner_product",

        "source_dataset":
            EMBEDDING_DATASET_FILE.name,

        "metadata_file":
            METADATA_FILE.name,

        "built_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),
    }

    with open(
        FAISS_MANIFEST_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            manifest,
            file,
            indent=2
        )

    # -------------------------------------------------
    # Final summary
    # -------------------------------------------------

    print()
    print(
        "FAISS index built successfully."
    )

    print(
        f"Vectors stored: "
        f"{index.ntotal}"
    )

    print(
        f"Vector dimension: "
        f"{vector_dimension}"
    )

    print(
        f"Index saved to:\n"
        f"{FAISS_INDEX_FILE}"
    )

    print(
        f"\nManifest saved to:\n"
        f"{FAISS_MANIFEST_FILE}"
    )


if __name__ == "__main__":
    build_faiss_index()