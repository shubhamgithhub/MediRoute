import json

import faiss
import numpy as np

from sentence_transformers import SentenceTransformer

from src.Src.backend.services.retrieval_config import (
    FAISS_INDEX_FILE,
    METADATA_FILE,
    FAISS_MANIFEST_FILE,
    EMBEDDING_MODEL_NAME,
    DEFAULT_TOP_K,
)


class FaissHospitalRetriever:

    def __init__(self):

        self._validate_files()

        # ---------------------------------------------
        # Load FAISS index
        # ---------------------------------------------

        self.index = faiss.read_index(
            str(FAISS_INDEX_FILE)
        )

        # ---------------------------------------------
        # Load hospital metadata
        # ---------------------------------------------

        with open(
            METADATA_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            self.metadata = json.load(
                file
            )

        # ---------------------------------------------
        # Load index manifest
        # ---------------------------------------------

        with open(
            FAISS_MANIFEST_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            self.manifest = json.load(
                file
            )

        # ---------------------------------------------
        # Validate alignment
        # ---------------------------------------------

        if self.index.ntotal != len(
            self.metadata
        ):
            raise ValueError(
                "FAISS index vector count does not "
                "match hospital metadata count"
            )

        manifest_model = self.manifest.get(
            "embedding_model"
        )

        if (
            manifest_model
            != EMBEDDING_MODEL_NAME
        ):
            raise ValueError(
                "Embedding model mismatch. "
                "Rebuild the FAISS index."
            )

        # ---------------------------------------------
        # Load the same model used to build the index
        # ---------------------------------------------

        self.model = SentenceTransformer(
            EMBEDDING_MODEL_NAME
        )

        print(
            "FAISS hospital retriever loaded."
        )

        print(
            f"Vectors available: "
            f"{self.index.ntotal}"
        )

    def _validate_files(self):

        required_files = [
            FAISS_INDEX_FILE,
            METADATA_FILE,
            FAISS_MANIFEST_FILE,
        ]

        missing_files = [
            str(file)
            for file in required_files
            if not file.exists()
        ]

        if missing_files:

            raise FileNotFoundError(
                "Required retrieval files are missing: "
                + ", ".join(missing_files)
            )

    def search(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K
    ) -> list[dict]:

        # ---------------------------------------------
        # Validate query
        # ---------------------------------------------

        if not query:
            return []

        query = query.strip()

        if not query:
            return []

        if top_k <= 0:
            return []

        top_k = min(
            top_k,
            self.index.ntotal
        )

        # ---------------------------------------------
        # Convert query text into an embedding
        # ---------------------------------------------

        query_embedding = (
            self.model.encode_query(
                [query],
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
        )

        query_embedding = np.asarray(
            query_embedding,
            dtype="float32"
        )

        # ---------------------------------------------
        # Search FAISS
        # ---------------------------------------------

        scores, indices = (
            self.index.search(
                query_embedding,
                top_k
            )
        )

        results = []

        # ---------------------------------------------
        # Convert vector positions into hospital data
        # ---------------------------------------------

        for rank, (
            vector_position,
            score
        ) in enumerate(
            zip(
                indices[0],
                scores[0]
            ),
            start=1
        ):

            if vector_position < 0:
                continue

            hospital = dict(
                self.metadata[
                    int(vector_position)
                ]
            )

            hospital[
                "semantic_rank"
            ] = rank

            hospital[
                "semantic_score"
            ] = float(score)

            results.append(
                hospital
            )

        return results