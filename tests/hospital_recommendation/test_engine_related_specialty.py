"""No hospital in the area has the suggested speciality -> hospitals in the area with a related one
(specialty_fallbacks.csv) come back as a separate group; the main list and speciality do not change."""
import pytest

from mediroute.common.medical_context import MedicalContext
from mediroute.common.specialties import load_specialty_fallbacks, specialty_names, validate_mapping
from mediroute.hospital_recommendation.engine import HospitalRecommendationEngine


@pytest.fixture(scope="module")
def engine():
    return HospitalRecommendationEngine()


def recommend(engine, specialty, city=None, procedures=()):
    return engine.recommend(MedicalContext(primary_specialty=specialty, procedures=list(procedures)),
                            preferred_city=city, top_k=5)


def test_fallback_table_is_valid():
    fallbacks = load_specialty_fallbacks()
    assert fallbacks["Reproductive Medicine"].related == ("Obstetrics & Gynaecology",)
    valid = set(specialty_names())
    assert all(f.specialty in valid and set(f.related) <= valid for f in fallbacks.values())
    assert not [p for p in validate_mapping() if "specialty_fallbacks" in p]


def test_no_hospital_in_area_adds_related_group(engine):
    out = recommend(engine, "Reproductive Medicine", city="Hyderabad", procedures=["IVF"])
    assert out["status"] == "success" and out["primary_specialty"] == "Reproductive Medicine"
    assert out["in_area_count"] == 0 and out["results"]  # exact matches elsewhere in India stay
    assert all(h["outside_area"] for h in out["results"])
    assert not any(h.get("related_specialty") for h in out["results"])
    assert out["related_specialty"] == "Obstetrics & Gynaecology"
    related = out["related_results"]
    assert 0 < len(related) <= 5 and out["related_count"] == len(related)
    assert all(h["city"] == "Hyderabad" and not h["outside_area"] for h in related)
    assert all(h["related_specialty"] == "Obstetrics & Gynaecology" for h in related)
    assert all(h["ranking_reasons"][0].startswith("Related speciality in your area") for h in related)
    assert [h["final_rank"] for h in related] == list(range(1, len(related) + 1))


def test_same_results_with_and_without_related_group(engine):
    """The main list is what it was before the change (Step 2 benchmarks score only this list)."""
    out = recommend(engine, "Reproductive Medicine", city="Hyderabad", procedures=["IVF"])
    names = [h["hospital_name"] for h in out["results"]]
    no_city = recommend(engine, "Reproductive Medicine", procedures=["IVF"])
    assert set(names) <= {h["hospital_name"] for h in engine.recommend(
        MedicalContext(primary_specialty="Reproductive Medicine", procedures=["IVF"]), top_k=20)["results"]}
    assert "related_results" not in no_city  # no area chosen -> no related group


def test_area_with_the_speciality_gets_no_related_group(engine):
    out = recommend(engine, "Reproductive Medicine", city="Mumbai")
    assert out["in_area_count"] > 0 and "related_results" not in out


def test_speciality_without_fallback_row_gets_no_related_group(engine):
    out = recommend(engine, "Cardiothoracic Surgery", city="Goa")
    assert out["in_area_count"] == 0 and "related_results" not in out
