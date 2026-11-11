"""Unit tests for the two Step 1 routes. The LLM is mocked, so Ollama is not needed."""

import json

import pytest

from mediroute.common.specialties import load_specialties, specialty_names
from mediroute.specialty_routing.routes import UNCLEAR, LLMRouter, RouteResult, RuleRouter, combine


def test_specialty_list_covers_hospital_table():
    """Every speciality in the hospital table is a Step 1 name, and Step 1's in_hospital_data flag
    is true exactly for the specialities that have hospitals."""
    import csv

    from mediroute.utils.paths import HOSPITALS_FILE

    with HOSPITALS_FILE.open(encoding="utf-8-sig") as handle:
        table = {s.strip() for row in csv.DictReader(handle)
                 for col in ("verified_specialties", "team_claimed_specialties")
                 for s in (row[col] or "").split(";") if s.strip() not in ("", "NA")}
    in_list = {s.name for s in load_specialties() if s.in_hospital_data}
    assert table <= set(specialty_names()), table - set(specialty_names())
    assert table == in_list


@pytest.mark.parametrize("text, expected", [
    ("My vision is blurry", "Ophthalmology"),
    ("severe knee arthritis, need total knee replacement", "Orthopaedics"),
    ("kidney stone with pain in the back", "Urology"),
    ("we want IVF after years of infertility", "Reproductive Medicine"),
])
def test_rules_route_known_terms(text, expected):
    assert RuleRouter().route(text).primary == expected


def test_rules_are_deterministic_and_explain():
    router = RuleRouter()
    first, second = router.route("chest pain and palpitations"), router.route("chest pain and palpitations")
    assert first.primary == second.primary == "Cardiology"
    assert first.ranked == second.ranked
    assert "chest pain" in first.evidence_terms


def test_rules_unclear_without_terms():
    result = RuleRouter().route("hello, I need some help")
    assert result.primary == UNCLEAR and result.ranked == []


def test_rules_prefer_longer_phrase():
    # "kidney stone" (Urology) must not also count "kidney" style single words twice
    result = RuleRouter().route("kidney stone")
    assert result.primary == "Urology"


def _mock_llm(monkeypatch, response: dict | Exception):
    router = LLMRouter(model="test-model")

    def fake_post(payload):
        if isinstance(response, Exception):
            raise response
        assert payload["format"]["properties"]["specialty"]["enum"][-1] == UNCLEAR
        return {"response": json.dumps(response)}

    monkeypatch.setattr(router, "_post", fake_post)
    return router


def test_llm_route_parses_valid_answer(monkeypatch):
    router = _mock_llm(monkeypatch, {"specialty": "Ophthalmology", "alternatives": ["Neurology"],
                                     "evidence_terms": ["blurry vision"]})
    result = router.route("My vision is blurry")
    assert result.primary == "Ophthalmology"
    assert result.ranked == ["Ophthalmology", "Neurology"]
    assert "blurry vision" in result.reason


def test_llm_route_rejects_names_outside_list(monkeypatch):
    router = _mock_llm(monkeypatch, {"specialty": "Liver Care", "alternatives": ["Eye Care"],
                                     "evidence_terms": []})
    result = router.route("My vision is blurry")
    assert result.primary == UNCLEAR and result.ranked == []


def test_llm_route_failure_is_flagged(monkeypatch):
    router = _mock_llm(monkeypatch, TimeoutError())
    result = router.route("anything")
    assert result.ok is False and result.primary == UNCLEAR


def test_prompt_lists_every_specialty():
    prompt = LLMRouter(model="test-model").build_prompt("test")
    assert all(name in prompt for name in specialty_names())


def _result(primary, ranked=None, ok=True):
    return RouteResult(primary=primary, ranked=ranked or ([primary] if primary != UNCLEAR else []), ok=ok)


def test_combine_confidence_levels():
    assert combine(_result("Cardiology"), _result("Cardiology"))[1] == "high"
    assert combine(_result("Cardiology", ["Cardiology", "Pulmonology"]), _result("Pulmonology"))[1] == "medium"
    assert combine(_result("Cardiology"), _result("Dermatology"))[1] == "low"


def test_combine_falls_back_to_rules_when_llm_fails():
    hybrid, confidence = combine(_result(UNCLEAR, ok=False), _result("Urology"))
    assert hybrid.primary == "Urology" and confidence == "low"
    assert hybrid.route == "hybrid:rules_fallback"


def test_llm_prompt_includes_speciality_boundaries():
    prompt = LLMRouter().build_prompt("planned CABG")
    assert "Route here when:" in prompt and "Not here:" in prompt
    assert "Route here when:" not in LLMRouter(prompt_version="specialty_v1").build_prompt("planned CABG")
