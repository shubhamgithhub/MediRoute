from src.Src.backend.medical_context import MedicalContext
from src.Src.backend.services.hospital_recommendation_engine import (
    HospitalRecommendationEngine,
)
from src.Src.backend.services.specialty_filter import SpecialtyFilter


def run_tests():
    print()
    print("STEP 11 - HOSPITAL RECOMMENDATION PIPELINE")
    print("=" * 60)

    engine = HospitalRecommendationEngine()
    specialty_filter = SpecialtyFilter()
    passed = 0
    failed = 0

    cardiology_context = MedicalContext(
        diagnoses=["coronary artery disease"],
        symptoms=["chest pain"],
        procedures=["CABG"],
        icd10_codes=["I25"],
        primary_specialty="Cardiology",
    )

    def check(test_id, condition, pass_message, fail_message):
        nonlocal passed, failed
        if condition:
            print(f"{test_id}: PASS - {pass_message}")
            passed += 1
        else:
            print(f"{test_id}: FAIL - {fail_message}")
            failed += 1

    valid = engine.recommend(cardiology_context, top_k=5)
    check("T001", valid["status"] == "success" and bool(valid["results"]),
          "Cardiology context returned recommendations", "Cardiology recommendation failed")

    scores = [result["final_score"] for result in valid["results"]]
    check("T002", scores == sorted(scores, reverse=True),
          "Final scores descending", "Final scores not descending")

    required_fields = {"semantic_score", "business_bonus", "final_score", "ranking_reasons", "final_rank"}
    check("T003", all(required_fields.issubset(result) for result in valid["results"]),
          "All reranking fields present", "A reranking field is missing")

    missing = engine.recommend(MedicalContext(), top_k=5)
    check("T004", missing["status"] == "needs_clarification",
          "Missing specialty asks for clarification", "Missing specialty status is wrong")

    eligible_positions = set(specialty_filter.filter_positions(
        engine.faiss_retriever.metadata, "Cardiology"
    ))
    eligible = all(result.get("vector_position") in eligible_positions for result in valid["results"])
    check("T005", eligible, "Returned hospitals are Cardiology eligible",
          "A returned hospital bypassed the specialty filter")

    check("T006", len(valid["results"]) <= 5, "top_k respected", "top_k was exceeded")

    city = None
    for hospital in engine.faiss_retriever.metadata:
        position = hospital.get("vector_position")
        if position in eligible_positions and hospital.get("city"):
            city = hospital["city"]
            break

    city_result = engine.recommend(cardiology_context, preferred_city=city, top_k=5)
    if city and city_result["status"] == "success":
        city_ok = all(
            str(result.get("city") or "").strip().casefold()
            == str(city).strip().casefold()
            for result in city_result["results"]
        )
    else:
        city_ok = False
    check("T007", city_ok, "Optional city filter restricted dynamic results",
          "City filter returned a different city or had no results")

    nonexistent = engine.recommend(
        cardiology_context,
        preferred_city="This City Does Not Exist",
        top_k=5,
    )
    check("T008", nonexistent["status"] == "no_location_match",
          "Nonexistent city returns no_location_match", "Nonexistent city did not return strict no-match status")

    numeric_scores = (
        valid["results"]
        and all(
            isinstance(result["semantic_score"], (int, float))
            and isinstance(result["final_score"], (int, float))
            for result in valid["results"]
        )
    )
    check("T009", numeric_scores, "Semantic and final scores are numeric",
          "A score is not numeric")

    reasons_ok = all(isinstance(result["ranking_reasons"], list) for result in valid["results"])
    check("T010", reasons_ok, "ranking_reasons is a list",
          "ranking_reasons is not a list")

    total = passed + failed
    accuracy = passed / total if total else 0.0
    print("=" * 60)
    print(f"Total tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Accuracy: {accuracy:.2%}")


if __name__ == "__main__":
    run_tests()
