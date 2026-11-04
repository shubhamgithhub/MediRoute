import json

from sklearn.feature_extraction.text import (
    TfidfVectorizer,
)

from sklearn.metrics.pairwise import (
    cosine_similarity,
)

from mediroute.backend.services.retrieval_config import (
    METADATA_FILE,
    DEFAULT_TOP_K,
)


class KeywordHospitalRetriever:

    def __init__(self):

        if not METADATA_FILE.exists():
            raise FileNotFoundError(
                f"Metadata file not found: "
                f"{METADATA_FILE}"
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

        if not self.metadata:
            raise ValueError(
                "Hospital metadata is empty"
            )

        # ---------------------------------------------
        # Extract searchable hospital text
        # ---------------------------------------------

        self.documents = [
            hospital.get(
                "hospital_search_text",
                ""
            )
            for hospital in self.metadata
        ]

        if not any(
            document.strip()
            for document in self.documents
        ):
            raise ValueError(
                "No searchable hospital text found"
            )

        # ---------------------------------------------
        # Build TF-IDF vocabulary
        #
        # ngram_range=(1, 2)
        # means:
        # single words + two-word phrases
        #
        # Example:
        # cardiology
        # cardiac surgery
        # coronary artery
        # ---------------------------------------------

        self.vectorizer = (
            TfidfVectorizer(
                lowercase=True,
                stop_words="english",
                ngram_range=(1, 2),
            )
        )

        # ---------------------------------------------
        # Convert all hospital documents into
        # TF-IDF vectors once at startup
        # ---------------------------------------------

        self.document_matrix = (
            self.vectorizer.fit_transform(
                self.documents
            )
        )

        print(
            "Keyword hospital retriever loaded."
        )

        print(
            f"Hospital documents: "
            f"{len(self.documents)}"
        )

    def search(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K
    ) -> list[dict]:

        # ---------------------------------------------
        # Validate input
        # ---------------------------------------------

        if not query:
            return []

        query = query.strip()

        if not query:
            return []

        if top_k <= 0:
            return []

        # ---------------------------------------------
        # Convert query into TF-IDF vector
        # ---------------------------------------------

        query_vector = (
            self.vectorizer.transform(
                [query]
            )
        )

        # ---------------------------------------------
        # Compare query to every hospital
        # ---------------------------------------------

        scores = cosine_similarity(
            query_vector,
            self.document_matrix
        )[0]

        # Highest score first
        ranked_positions = (
            scores
            .argsort()[::-1]
        )

        results = []

        for position in ranked_positions:

            score = float(
                scores[position]
            )

            # Skip hospitals with zero keyword match
            if score <= 0:
                continue

            hospital = dict(
                self.metadata[
                    int(position)
                ]
            )

            hospital[
                "keyword_rank"
            ] = len(results) + 1

            hospital[
                "keyword_score"
            ] = score

            results.append(
                hospital
            )

            if len(results) >= top_k:
                break

        return results