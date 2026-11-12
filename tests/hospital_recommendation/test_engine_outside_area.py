"""Fewer than 3 hospitals in the patient's area -> the list is filled from outside it, as a separate group."""
import pytest

from mediroute.common.medical_context import MedicalContext
from mediroute.hospital_recommendation.engine import HospitalRecommendationEngine


@pytest.fixture(scope="module")
def engine():
    return HospitalRecommendationEngine()


def recommend(engine, specialty, city=None, state=None):
    return engine.recommend(MedicalContext(primary_specialty=specialty), preferred_city=city,
                            preferred_state=state, top_k=5)


def test_small_area_is_filled_after_in_area_hospitals(engine):
    out = recommend(engine, "Reproductive Medicine", city="Pune")
    in_area = [h for h in out["results"] if not h["outside_area"]]
    outside = [h for h in out["results"] if h["outside_area"]]
    assert out["status"] == "success"
    assert 0 < len(in_area) < engine.MIN_IN_AREA and outside
    assert out["in_area_count"] == len(in_area) and out["outside_area_count"] == len(outside)
    # in-area hospitals always come first; same state before the rest of India
    assert out["results"][:len(in_area)] == in_area
    groups = [h["area_group"] for h in outside]
    assert groups == sorted(groups, key=lambda g: g != "Elsewhere in the same state")
    assert all(h["city"] == "Pune" for h in in_area)
    assert all(h["ranking_reasons"][0].startswith("Outside your chosen area") for h in outside)
    assert [h["final_rank"] for h in out["results"]] == list(range(1, len(out["results"]) + 1))


def test_big_area_is_not_filled(engine):
    out = recommend(engine, "Urology", city="Mumbai")
    assert out["outside_area_count"] == 0
    assert all(not h["outside_area"] for h in out["results"])


def test_unknown_city_keeps_strict_no_match(engine):
    assert recommend(engine, "Cardiology", city="This City Does Not Exist")["status"] == "no_location_match"
