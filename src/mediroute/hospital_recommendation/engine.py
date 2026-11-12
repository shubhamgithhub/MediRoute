from mediroute.common.locations import load_cities, resolve_location
from mediroute.hospital_recommendation.retrieval.faiss_retriever import FaissHospitalRetriever
from mediroute.hospital_recommendation.retrieval.filtered_faiss_retriever import FilteredFaissHospitalRetriever
from mediroute.hospital_recommendation.specialty_filter import SpecialtyFilter
from mediroute.hospital_recommendation.retrieval.semantic_query_builder import SemanticQueryBuilder
from mediroute.hospital_recommendation.ranking.hospital_reranker import HospitalReranker


class HospitalRecommendationEngine:
    """Runs eligibility filtering, semantic retrieval, and transparent reranking.

    When the patient's area (a known city / search area, or a state) has fewer than MIN_IN_AREA
    hospitals for the speciality, the list is filled with hospitals outside it, nearest first by
    administrative area (same state, then elsewhere in India; cities.csv has no coordinates).
    They come after every in-area hospital and carry outside_area=True and area_group, so the
    screen shows them as a separate group. An unknown city keeps the strict "no_location_match".
    """

    MIN_IN_AREA = 3

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

        # fill-up candidates outside the area: same state first, then anywhere (known areas only)
        known_area = (allowed_cities is not None and self._known_cities(allowed_cities)) or (
            allowed_cities is None and bool(preferred_state_value))
        outside_groups = []
        if known_area and len(location_positions) < self.MIN_IN_AREA:
            outside_groups = self._outside_groups(specialty_positions, set(location_positions), allowed_cities,
                                                  preferred_state_value)

        if not location_positions and not any(positions for _, positions in outside_groups):
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
        final_results, retrieval_count = self._rank_group(
            context, semantic_query, location_positions, primary_specialty, top_k)
        in_area_count = len(final_results)
        area_label = preferred_city or preferred_state or ""
        for group, positions in outside_groups:
            room = top_k - len(final_results)
            if room <= 0:
                break
            ranked, found = self._rank_group(context, semantic_query, positions, primary_specialty, room)
            retrieval_count += found
            for hospital in ranked:
                hospital["outside_area"] = True
                hospital["area_group"] = group
                hospital["ranking_reasons"] = [f"Outside your chosen area ({area_label}): {group.lower()}"] + \
                    hospital.get("ranking_reasons", [])
            final_results.extend(ranked)
        for rank, hospital in enumerate(final_results, start=1):
            hospital["final_rank"] = rank
            hospital.setdefault("outside_area", False)

        return {
            "status": "success",
            "primary_specialty": primary_specialty,
            "preferred_city": preferred_city,
            "preferred_state": preferred_state,
            "specialty_candidate_count": len(specialty_positions),
            "location_candidate_count": len(location_positions),
            "in_area_count": in_area_count,
            "outside_area_count": len(final_results) - in_area_count,
            "semantic_query": semantic_query,
            "retrieval_candidate_count": retrieval_count,
            "count": len(final_results),
            "results": final_results,
        }

    def _rank_group(self, context, semantic_query, positions, primary_specialty, top_k):
        """Filter -> FAISS (3 x top_k) -> rerank within one group of hospitals."""
        if not positions or top_k <= 0:
            return [], 0
        found = self.filtered_retriever.search(
            query=semantic_query,
            allowed_positions=positions,
            top_k=min(max(top_k * 3, top_k), len(positions)),
        )
        for hospital in found:
            hospital["specialty_evidence"] = self.specialty_filter.specialty_evidence(hospital, primary_specialty)
        return self.reranker.rerank(found, patient_procedures=context.procedures, top_k=top_k), len(found)

    @staticmethod
    def _known_cities(cities):
        known = {c.name for c in load_cities()}
        return bool(cities) and set(cities) <= known

    def _outside_groups(self, specialty_positions, in_area, allowed_cities, preferred_state_value):
        """[(label, positions)] outside the area: same state (when a city was chosen), then elsewhere."""
        if allowed_cities is not None:
            states = {c.state.casefold() for c in load_cities() if c.name in allowed_cities}
        else:
            states = {preferred_state_value}
        same_state, elsewhere = [], []
        for hospital in self.faiss_retriever.metadata:
            position = hospital.get("vector_position")
            if position not in specialty_positions or position in in_area:
                continue
            state = str(hospital.get("state") or "").strip().casefold()
            (same_state if state in states and allowed_cities is not None else elsewhere).append(position)
        return [("Elsewhere in the same state", same_state), ("Elsewhere in India", elsewhere)]
