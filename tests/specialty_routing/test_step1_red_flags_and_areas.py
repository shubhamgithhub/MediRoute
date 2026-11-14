"""14 Nov: red-flag emergency routing and the multi-body-area question (Step 1, stages 2 and 3b)."""

from __future__ import annotations

import pytest

from mediroute.common.specialties import count_body_areas, validate_mapping
from mediroute.specialty_routing.step1.evidence import EvidenceExtractor
from mediroute.specialty_routing.step1.lookup import LookupIndex
from mediroute.specialty_routing.step1.ollama_client import LLMCall
from mediroute.specialty_routing.step1.pipeline import (BODY_AREAS, MULTI_AREA_ANSWER, NOT_SURE, Step1Input,
                                                        Step1Pipeline)
from mediroute.specialty_routing.step1.safety import check_emergency, routes_to_emergency
from mediroute.specialty_routing.step1.voters import LLMVoter
from tests.specialty_routing.test_step1_pipeline import ENTRIES, FakeEncoder


# ---------------------------------------------------------------- red flags (stage 2)
@pytest.mark.parametrize("text,rule", [
    ("I'm sweating a lot and can't catch my breath. My heart is racing and my chest hurts.",  # G004
     "chest_pain_with_breathlessness_or_sweating"),
    ("headaches and chest pains for a few days, today the dizziness got worse", "chest_pain_with_breathlessness_or_sweating"),
    ("high fever, shortness of breath, my heart is racing", "breathless_with_racing_heart"),
    ("I feel dizzy and confused, and I have lost my sight", "sudden_loss_of_sight"),
    ("my back hurts, I feel weak and disoriented", "new_confusion"),
])
def test_red_flags_route_to_emergency(text, rule):
    result = check_emergency(text)
    assert rule in result["matched_rules"] and routes_to_emergency(result)


@pytest.mark.parametrize("text", [
    "heartburn and indigestion, and chest pain when I lean forward or lie down",  # G023: reflux, not a red flag
    "I get chest tightness when I climb stairs and it goes away when I rest",
    "I am confused about which hospital to choose for knee replacement",
    "panic attacks with racing heart, cardiology tests were normal",
    "I can't see clearly when reading, need glasses",
])
def test_no_false_red_flags(text):
    assert not routes_to_emergency(check_emergency(text))


def test_suicidal_intent_alone_keeps_normal_routing():
    result = check_emergency("I have been thinking about ending my life")
    assert result["is_emergency"] and not routes_to_emergency(result)


# ---------------------------------------------------------------- body areas (data + counting)
def test_area_files_are_valid():
    assert validate_mapping() == []
    assert BODY_AREAS[-2:] == [MULTI_AREA_ANSWER, NOT_SURE]


@pytest.mark.parametrize("tags,count", [
    (["ear", "nose_sinuses", "throat_mouth"], 1),                  # ear, nose and throat = one area
    (["digestion", "nausea_vomiting"], 1),
    (["digestion", "throat_mouth"], 1),                            # reflux pair
    (["digestion", "throat_mouth", "ear"], 2),                     # ...but not with the ear
    (["nose_sinuses", "throat_mouth", "lungs_breathing"], 1),      # cold pair
    (["headache", "nausea_vomiting"], 1),                          # migraine pair
    (["nausea_vomiting", "digestion", "brain_nerves"], 2),         # G050: vomiting + dizziness
    (["eyes", "headache"], 2),                                     # G045
    (["skin_hair", "general"], 1),                                 # fever is not an area
    (["general"], 0),
])
def test_count_body_areas(tags, count):
    assert count_body_areas(tags)["count"] == count


# ---------------------------------------------------------------- pipeline flow
class AreaClient:
    """Evidence v2 replies keyed by a word in the message; the LLM voter answers from SPEC."""

    model = "fake-llm"
    EVIDENCE = {
        "vomiting": {"conditions": ["vomiting", "dizziness"], "procedures": [], "body_parts": [], "named_diagnoses": [],
                     "symptom_areas": [{"phrase": "vomiting", "tag": "nausea_vomiting"},
                                       {"phrase": "dizziness", "tag": "brain_nerves"}]},
        "heartburn": {"conditions": ["heartburn", "sore throat"], "procedures": [], "body_parts": [], "named_diagnoses": [],
                      "symptom_areas": [{"phrase": "heartburn", "tag": "digestion"},
                                        {"phrase": "sore throat", "tag": "throat_mouth"}]},
        "asthma": {"conditions": ["asthma", "headaches"], "procedures": [], "body_parts": [], "named_diagnoses": ["asthma"],
                   "symptom_areas": [{"phrase": "wheezing", "tag": "lungs_breathing"},
                                     {"phrase": "headaches", "tag": "headache"}]},
    }
    SPEC = {"vomiting": "Gastroenterology", "heartburn": "Gastroenterology", "asthma": "Pulmonology"}

    def warm_up(self) -> None:
        pass

    def generate_json(self, prompt: str, schema: dict, purpose: str) -> LLMCall:
        message = prompt.rsplit("Patient message:", 1)[-1].lower()
        if purpose == "evidence_extraction":
            for key, value in self.EVIDENCE.items():
                if key in message:
                    return LLMCall(True, parsed=value, details={"purpose": purpose})
            return LLMCall(True, parsed={"conditions": [], "procedures": [], "body_parts": []}, details={"purpose": purpose})
        for key, value in self.SPEC.items():
            if key in message:
                return LLMCall(True, parsed={"specialty": value, "alternatives": [], "evidence_terms": [key]},
                               details={"purpose": purpose})
        return LLMCall(True, parsed={"specialty": "Unclear", "alternatives": [], "evidence_terms": []},
                       details={"purpose": purpose})


def make_pipeline() -> Step1Pipeline:
    from mediroute.specialty_routing.step1.judge import LLMJudge
    from mediroute.specialty_routing.step1.ollama_client import DisabledLLMClient
    client = AreaClient()
    index = LookupIndex(ENTRIES, encoder=FakeEncoder(), cache=False)
    return Step1Pipeline(index=index, client=client, extractor=EvidenceExtractor(client), llm_voter=LLMVoter(client),
                         judge=LLMJudge(client=DisabledLLMClient(), index=index))


def test_red_flag_routes_to_emergency_medicine_without_llm():
    out = make_pipeline().analyze(Step1Input(text="I can't catch my breath, my heart is racing and my chest hurts"))
    assert out["decision"] == "emergency_rule" and out["suggested_specialty"] == "Emergency Medicine"
    assert out["emergency"] and out["emergency_message"]


def test_two_body_areas_ask_then_more_than_one_gives_general_medicine():
    pipe = make_pipeline()
    text = "I have been vomiting for days and I get dizziness"
    first = pipe.analyze(Step1Input(text=text))
    assert first["decision"] == "clarification_required"
    assert "several parts of the body" in first["reason"] and "More than one" in first["clarification"]["message"]
    options = next(f for f in first["clarification"]["fields"] if f["name"] == "body_area")["options"]
    assert MULTI_AREA_ANSWER in options
    second = pipe.analyze(Step1Input(text=text, clarification={"body_area": MULTI_AREA_ANSWER},
                                     clarification_round=1, parent_request_id=first["request_id"]))
    assert second["decision"] == "multi_area_general_medicine" and second["suggested_specialty"] == "General Medicine"
    assert "general physician" in second["reason"]


def test_not_sure_after_the_area_question_also_gives_general_medicine():
    pipe = make_pipeline()
    text = "I have been vomiting for days and I get dizziness"
    out = pipe.analyze(Step1Input(text=text, clarification={"body_area": NOT_SURE}, clarification_round=1))
    assert out["decision"] == "multi_area_general_medicine"


def test_neighbour_pair_does_not_ask():
    out = make_pipeline().analyze(Step1Input(text="heartburn every night and a sore throat"))
    assert "several parts" not in (out.get("reason") or "")


def test_named_diagnosis_skips_the_area_question():
    out = make_pipeline().analyze(Step1Input(text="I have asthma, wheezing and headaches"))
    assert "several parts" not in (out.get("reason") or "")
    assert out["decision"] != "multi_area_general_medicine"
