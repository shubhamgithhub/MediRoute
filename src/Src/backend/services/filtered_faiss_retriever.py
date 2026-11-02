import faiss
import numpy as np


class FilteredFaissHospitalRetriever:
    """Searches FAISS only over an explicitly allowed set of hospital positions."""

    def __init__(self, faiss_retriever):
        self.faiss_retriever = faiss_retriever
        self.model = faiss_retriever.model
        self.index = faiss_retriever.index
        self.metadata = faiss_retriever.metadata

    def search(self, query, allowed_positions, top_k=10):
        if not query or not str(query).strip():
            return []
        if not allowed_positions:
            return []
        if top_k <= 0:
            return []

        unique_positions = []
        seen = set()
        for position in allowed_positions:
            try:
                position = int(position)
            except (TypeError, ValueError):
                continue
            if 0 <= position < self.index.ntotal and position < len(self.metadata):
                if position not in seen:
                    seen.add(position)
                    unique_positions.append(position)

        if not unique_positions:
            return []

        vectors = []
        for position in unique_positions:
            vectors.append(self.index.reconstruct(position))
        candidate_vectors = np.asarray(vectors, dtype="float32")

        # A temporary inner-product index limits semantic retrieval to eligible hospitals.
        candidate_index = faiss.IndexFlatIP(candidate_vectors.shape[1])
        candidate_index.add(candidate_vectors)

        query_embedding = self.model.encode_query(
            [str(query).strip()],
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        query_embedding = np.asarray(query_embedding, dtype="float32")

        result_count = min(top_k, len(unique_positions))
        scores, local_indices = candidate_index.search(query_embedding, result_count)

        results = []
        for semantic_rank, (local_position, score) in enumerate(
            zip(local_indices[0], scores[0]), start=1
        ):
            if local_position < 0:
                continue
            global_position = unique_positions[int(local_position)]
            hospital = dict(self.metadata[global_position])
            hospital["semantic_rank"] = semantic_rank
            hospital["semantic_score"] = float(score)
            results.append(hospital)

        return results
