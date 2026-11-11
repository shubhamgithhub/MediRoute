from mediroute.common.locations import resolve_location
from mediroute.hospital_recommendation.retrieval.faiss_retriever import FaissHospitalRetriever
from mediroute.hospital_recommendation.retrieval.filtered_faiss_retriever import FilteredFaissHospitalRetriever
from mediroute.hospital_recommendation.specialty_filter import SpecialtyFilter
from mediroute.hospital_recommendation.retrieval.semantic_query_builder import SemanticQueryBuilder
from mediroute.hospital_recommendation.ranking.hospital_reranker import HospitalReranker


class HospitalRecommendationEngine:
    """Runs eligibility filtering, semantic retrieval, and transparent reranking."""

    def __init__(self, faiss_retriever=None):
        self.faiss_retriever = faiss_retriever or FaissHospitalRetriever()
        self.filtered_retriever = FilteredFaissHospitalRetriever(self.faiss_retriever)
        self.specialty_filter = SpecialtyFilter()
        self.semantic_query_builder = SemanticQueryBuilder()
        self.reranker = HospitalReranker()

    def _normalize_location(self, value):
        if value is None:
            return None
        text = str(value).strip()
        if not text or text.casefold() == "no preference":
            return None
        return text.casefold()

    def recommend(self, context, preferred_city=None, preferred_state=None, top_k=5):
        top_k = max(1, min(20, int(top_k)))
        preferred_city_value = self._normalize_location(preferred_city)
        preferred_state_value = self._normalize_location(preferred_state)

        if not context.primary_specialty or not str(context.primary_specialty).strip():
            return {
                "status": "needs_clarification",
                "primary_specialty": None,
                "preferred_city": preferred_city,
                "preferred_state": preferred_state,
                "specialty_candidate_count": 0,
                "location_candidate_count": 0,
                "semantic_query": "",
                "retrieval_candidate_count": 0,
                "count": 0,
                "results": [],
            }

        primary_specialty = self.specialty_filter.normalize_specialty(context.primary_specialty)
        specialty_positions = self.specialty_filter.filter_positions(
            self.faiss_retriever.metadata, primary_specialty
        )

        if not specialty_positions:
            return {
                "status": "no_specialty_match",
                "primary_specialty": primary_specialty,
                "preferred_city": preferred_city,
                "preferred_state": preferred_state,
                "specialty_candidate_count": 0,
                "location_candidate_count": 0,
                "semantic_query": "",
                "retrieval_candidate_count": 0,
                "count": 0,
                "results": [],
            }

        # a city or a search area ("Delhi NCR" = New Delhi + Gurugram + Noida), from data/processed/cities.csv
        allowed_cities = resolve_location(preferred_city) if preferred_city_value else None
        location_positions = []
        specialty_position_set = set(specialty_positions)
        for hospital in self.faiss_retriever.metadata:
            position = hospital.get("vector_position")
            if position not in specialty_position_set:
                continue

            if allowed_cities is not None:
                if str(hospital.get("city") or "").strip() not in allowed_cities:
                    continue
            elif preferred_state_value:
                state = str(hospital.get("state") or "").strip().casefold()
                if state != preferred_state_value:
                    continue
            location_positions.append(position)

        if not location_positions:
            return {
                "status": "no_location_match",
                "primary_specialty": primary_specialty,
                "preferred_city": preferred_city,
                "preferred_state": preferred_state,
                "specialty_candidate_count": len(specialty_positions),
                "location_candidate_count": 0,
                "semantic_query": "",
                "retrieval_candidate_count": 0,
                "count": 0,
                "results": [],
            }

        semantic_query = self.semantic_query_builder.build(context)
        retrieval_k = min(max(top_k * 3, top_k), len(location_positions))
        retrieval_results = self.filtered_retriever.search(
            query=semantic_query,
            allowed_positions=location_positions,
            top_k=retrieval_k,
        )
        for hospital in retrieval_results:
            hospital["specialty_evidence"] = self.specialty_filter.specialty_evidence(hospital, primary_specialty)
        final_results = self.reranker.rerank(
            retrieval_results,
            patient_procedures=context.procedures,
            top_k=top_k,
        )

        return {
            "status": "success",
            "primary_specialty": primary_specialty,
            "preferred_city": preferred_city,
            "preferred_state": preferred_state,
            "specialty_candidate_count": len(specialty_positions),
            "location_candidate_count": len(location_positions),
            "semantic_query": semantic_query,
            "retrieval_candidate_count": len(retrieval_results),
            "count": len(final_results),
            "results": final_results,
        }
