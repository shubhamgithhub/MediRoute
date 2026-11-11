"""Step 1 and Step 2 read the same data files; these tests fail if they drift apart again."""

import json

import pandas as pd
import pytest

from mediroute.common.locations import city_names, resolve_location
from mediroute.common.specialties import (
    hospital_label_map,
    hospital_specialty_counts,
    lay_terms,
    load_specialties,
    specialty_names,
    validate_mapping,
)
from mediroute.hospital_recommendation.ranking.hospital_reranker import HospitalReranker
from mediroute.hospital_recommendation.specialty_filter import SpecialtyFilter
from mediroute.utils.paths import HOSPITALS_FILE, TEAM_150_SHEET_FILE, VECTOR_STORE_DIR

STEP1 = set(specialty_names())


@pytest.fixture(scope="module")
def hospitals():
    return pd.read_csv(HOSPITALS_FILE, dtype=str, keep_default_na=False)


def _names(value):
    return {s.strip() for s in str(value).split(";") if s.strip() and s.strip() != "NA"}


# ---------------------------------------------------------------- one speciality list
def test_mapping_table_is_valid():
    """Every rule in specialty_mapping.csv points to the master list, once, with an allowed type."""
    assert validate_mapping() == []


def test_every_team_sheet_label_is_mapped():
    sheet = pd.read_excel(TEAM_150_SHEET_FILE, sheet_name="Hospitals_150")
    labels = {s.strip().casefold() for col in ("verified_specialties", "verified_subspecialties")
              for v in sheet[col].dropna() for s in str(v).split(";") if s.strip()}
    assert labels <= set(hospital_label_map()), sorted(labels - set(hospital_label_map()))


def test_weak_lay_terms_are_not_strong_evidence():
    strong = {r.value for r in lay_terms("strong")}
    assert {"kidney stone", "cataract"} <= strong
    assert not {"baby", "child", "eye", "bleeding"} & strong


def test_neurosciences_reaches_neurology_and_neurosurgery():
    assert SpecialtyFilter().canonical_set("Neurosciences") == {"Neurology", "Neurosurgery"}
    assert SpecialtyFilter().canonical_set("General Surgery") == set()  # NONE: not a routing speciality


# ---------------------------------------------------------------- one hospital table
def test_hospital_table_is_consistent(hospitals):
    assert hospitals["hospital_id"].is_unique
    assert set(hospitals["city"]) <= set(city_names())
    for col in ("verified_specialties", "team_claimed_specialties"):
        bad = {s for v in hospitals[col] for s in _names(v)} - STEP1
        assert not bad, (col, bad)
    assert set(hospitals["record_origin"]) <= {"team city lists", "team 150 sheet"}
    team_detail = hospitals[hospitals["detail_source"] != ""]
    assert (team_detail["team150_id"] != "").all()


def test_team_sheet_never_overrides_verification(hospitals):
    """Accreditation and verification come from the master's own checks, in its formats."""
    assert set(hospitals["nabh_status"]) <= {"Accredited", "Certified", "Empaneled", "Needs verification",
                                             "Not found in NABH directory"}
    assert set(hospitals["jci_status"]) <= {"Accredited", "Not listed"}
    assert set(hospitals["verification_status"]) <= {"Verified", "Partially verified", "Needs verification"}


def test_step1_hospital_flag_comes_from_the_hospital_table(hospitals):
    counts = hospital_specialty_counts()
    for spec in load_specialties():
        assert spec.in_hospital_data == (counts.get(spec.name, 0) > 0), spec.name
    assert counts["Neurology"] > 20  # was 2 before the label mapping was completed


def test_search_index_matches_hospital_table(hospitals):
    metadata = json.load(open(VECTOR_STORE_DIR / "hospital_metadata.json", encoding="utf-8"))
    assert [m["hospital_id"] for m in metadata] == list(hospitals["hospital_id"])


# ---------------------------------------------------------------- one city list
@pytest.mark.parametrize("choice, must_include", [
    ("Delhi NCR", {"New Delhi", "Gurugram"}),
    ("Gurugram", {"New Delhi", "Gurugram"}),   # a city searches its whole area
    ("mumbai", {"Mumbai", "Navi Mumbai"}),
    ("Chennai", {"Chennai"}),
])
def test_search_areas(choice, must_include):
    assert must_include <= resolve_location(choice)


def test_no_preference_and_unknown_city():
    assert resolve_location("No preference") is None
    assert resolve_location("") is None
    assert resolve_location("Atlantis") == {"Atlantis"}  # exact only, so the patient is asked


# ---------------------------------------------------------------- ranking uses the new fields
def _hospital(**fields):
    base = {"hospital_id": "H1", "semantic_score": 0.4, "procedures": "", "verification_status": "",
            "nabh_status": "", "jci_status": "", "international_patient_service": "", "evidence_quality_score": ""}
    return {**base, **fields}


@pytest.mark.parametrize("patient, hospital_list, expected", [
    ("CABG", "TAVR; Robotic CABG", "Robotic CABG"),
    ("knee replacement", "Total Knee Arthroplasty; ACL repair", "Total Knee Arthroplasty"),
    ("bypass surgery", "CABG", "CABG"),
    ("cataract surgery", "Total Knee Arthroplasty", None),
])
def test_procedure_matching_by_words(patient, hospital_list, expected):
    reranker = HospitalReranker()
    assert reranker._match_procedure(patient, reranker._split_values(hospital_list)) == expected


def test_master_value_formats_score_and_website_evidence_ranks_first():
    reranker = HospitalReranker()
    verified = _hospital(hospital_id="A", specialty_evidence="website", verification_status="Verified",
                         nabh_status="Accredited", international_patient_service="Available",
                         evidence_quality_score="High")
    team_only = _hospital(hospital_id="B", specialty_evidence="team list", verification_status="Needs verification",
                          nabh_status="Needs verification", international_patient_service="Not found on website")
    ranked = reranker.rerank([team_only, verified])
    assert [r["hospital_id"] for r in ranked] == ["A", "B"]
    assert "Speciality confirmed on the hospital's website" in ranked[0]["ranking_reasons"]
    assert "NABH accredited" in ranked[0]["ranking_reasons"]
    assert ranked[1]["business_bonus"] == 0
    assert any("not yet confirmed" in r for r in ranked[1]["ranking_reasons"])
