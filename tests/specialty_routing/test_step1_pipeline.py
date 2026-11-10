"""Step 1 voting pipeline, tested without Ollama or the embedding model (both faked)."""

from __future__ import annotations

import re

import numpy as np
import pytest

from mediroute.specialty_routing.step1.evidence import EvidenceExtractor, verify_phrase
from mediroute.specialty_routing.step1.lookup import LookupEntry, LookupIndex, icd_specialty_for
from mediroute.specialty_routing.step1.ollama_client import LLMCall
from mediroute.specialty_routing.step1.pipeline import Step1Input, Step1Pipeline
from mediroute.specialty_routing.step1.protect import redact
from mediroute.specialty_routing.step1.safety import check_emergency
from mediroute.specialty_routing.step1.voters import LLMVoter

ENTRIES = [
    LookupEntry("icd:M17", "icd10cm", "M17", "Osteoarthritis of knee", "Orthopaedics"),
    LookupEntry("cghs:OR1", "cghs", "OR1", "Total Knee Replacement", "Orthopaedics"),
    LookupEntry("cghs:CV013", "cghs", "CV013", "Coronary Artery Bypass Graft surgery (CABG)", "Cardiothoracic Surgery"),
    LookupEntry("icd:I25", "icd10cm", "I25", "Chronic ischemic heart disease", "Cardiology"),
    LookupEntry("icd:R53", "icd10cm", "R53", "Malaise and fatigue weakness", "General Medicine"),
    LookupEntry("icd:H25", "icd10cm", "H25", "Age-related cataract", "Ophthalmology"),
]


class FakeEncoder:
    """Bag-of-words vectors: enough to make 'knee replacement' close to 'Total Knee Replacement'."""

    def __init__(self) -> None:
        self.vocab: dict[str, int] = {}

    def encode(self, texts, **_kwargs):
        rows = []
        for text in texts:
            vec = np.zeros(256, dtype=np.float32)
            for token in re.findall(r"[a-z]+", text.lower()):
                vec[self.vocab.setdefault(token, len(self.vocab) % 256)] += 1
            norm = np.linalg.norm(vec)
            rows.append(vec / norm if norm else vec)
        return np.vstack(rows)


class FakeClient:
    """Answers the two prompts from tables keyed by a word in the text. Set `down` to simulate Ollama off."""

    model = "fake-llm"

    def __init__(self, evidence: dict[str, dict], specialty: dict[str, str], down: bool = False) -> None:
        self.evidence, self.specialty, self.down = evidence, specialty, down

    def warm_up(self) -> None:
        pass

    def generate_json(self, prompt: str, schema: dict, purpose: str) -> LLMCall:
        if self.down:
            return LLMCall(False, error="ConnectionRefusedError: fake", details={"purpose": purpose})
        message = prompt.rsplit("Patient message:", 1)[-1].lower()
        if purpose == "evidence_extraction":
            for key, value in self.evidence.items():
                if key in message:
                    return LLMCall(True, parsed=value, raw_response=str(value), details={"purpose": purpose})
            return LLMCall(True, parsed={"conditions": [], "procedures": [], "body_parts": []}, details={"purpose": purpose})
        for key, value in self.specialty.items():
            if key in message:
                parsed = {"specialty": value, "alternatives": [], "evidence_terms": [key]}
                return LLMCall(True, parsed=parsed, raw_response=str(parsed), details={"purpose": purpose})
        return LLMCall(True, parsed={"specialty": "Unclear", "alternatives": [], "evidence_terms": []},
                       details={"purpose": purpose})


EVIDENCE = {
    "osteoarthritis": {"conditions": ["osteoarthritis of both knees"], "procedures": ["knee replacement"], "body_parts": ["knees"]},
    "cabg": {"conditions": [], "procedures": ["CABG"], "body_parts": []},
    "weakness": {"conditions": ["weakness"], "procedures": [], "body_parts": []},
    "invented": {"conditions": ["pancreatic cancer"], "procedures": [], "body_parts": []},
}
SPECIALTY = {"osteoarthritis": "Orthopaedics", "cabg": "Cardiothoracic Surgery", "weakness": "General Medicine",
             "cataract": "Ophthalmology"}


def make_pipeline(down: bool = False) -> Step1Pipeline:
    client = FakeClient(EVIDENCE, SPECIALTY, down=down)
    index = LookupIndex(ENTRIES, encoder=FakeEncoder(), cache=False)
    return Step1Pipeline(index=index, client=client, extractor=EvidenceExtractor(client), llm_voter=LLMVoter(client))


# ---------------------------------------------------------------- protect and safety
def test_redact_removes_contacts_and_ids_but_keeps_clinical_numbers():
    text = "Call +91 98765 43210 or mail a.b@x.com, passport K1234567. eGFR 8, fibroid 14x9 cm on 2026-11-10."
    redacted, counts = redact(text)
    assert "[PHONE]" in redacted and "[EMAIL]" in redacted and "[ID]" in redacted
    assert "eGFR 8" in redacted and "14x9 cm" in redacted and "2026-11-10" in redacted
    assert counts == {"email": 1, "phone": 1, "id_number": 1}


@pytest.mark.parametrize("text,expected", [
    ("crushing chest pain and he cannot breathe", True),
    ("her face is drooping on one side", True),
    ("I have been thinking about ending my life", True),
    ("chest pain when I climb stairs", False),  # chest pain alone is not a red flag
    ("knee replacement", False),
])
def test_emergency_rules(text, expected):
    assert check_emergency(text)["is_emergency"] is expected


def test_suicidal_intent_gets_crisis_message():
    result = check_emergency("I want to end my life")
    assert result["matched_rules"] == ["suicidal_intent"] and "Tele-MANAS" in result["message"]


# ---------------------------------------------------------------- evidence and lookup
def test_verify_phrase_allows_typos_and_abbreviations_but_drops_invented_text():
    source = {"neede", "knee", "replacment", "surgery", "oa"}
    assert verify_phrase("knee replacement", source)[0]  # typo in the source
    assert verify_phrase("osteoarthritis", {"oa", "knee"})[0]  # abbreviation
    assert not verify_phrase("pancreatic cancer", source)[0]


@pytest.mark.parametrize("phrase,generic", [
    ("treatment", True), ("hospital", True), ("suggest treatment hospital in Mumbai", True),
    ("since last 1 month", True), ("best doctor", True),
    ("eye infection", False), ("knee replacement", False), ("bypass surgery", False), ("PSA test", False),
])
def test_generic_words_are_not_evidence(phrase, generic):
    from mediroute.specialty_routing.step1.evidence import is_generic
    assert is_generic(phrase) is generic


def test_eye_infection_query_drops_generic_evidence():
    """Regression for trace 3b2c6e933acb: 'treatment' and 'hospital' were kept as procedures and
    pushed the keyword voter to Obstetrics & Gynaecology."""
    llm_output = {"conditions": ["eye infection"], "procedures": ["treatment", "hospital"], "body_parts": ["eye"]}
    client = FakeClient({"eye infection": llm_output}, {"eye infection": "Ophthalmology"})
    evidence = EvidenceExtractor(client).extract(
        "eye infection since last 1 month,suggest treatment hospital in Mumbai")
    assert evidence.kept["procedures"] == []
    assert {d["phrase"] for d in evidence.dropped} == {"treatment", "hospital"}
    assert evidence.routing_phrases == ["eye infection"]


def test_lay_terms_are_in_the_lookup_list():
    from mediroute.specialty_routing.step1.lookup import _lay_term_entries
    lay = {(e.text, e.specialty) for e in _lay_term_entries()}
    assert ("eye infection", "Ophthalmology") in lay
    assert ("ear discharge", "ENT") in lay


def test_icd_narrowest_range_wins():
    blocks = [{"code_from": "I80", "code_to": "I89", "specialty": "Cardiothoracic Surgery"},
              {"code_from": "I85", "code_to": "I85", "specialty": "Gastroenterology"}]
    assert icd_specialty_for("I850", blocks) == "Gastroenterology"
    assert icd_specialty_for("I83", blocks) == "Cardiothoracic Surgery"


# ---------------------------------------------------------------- decisions
def test_majority_with_evidence_selects_specialty():
    result = make_pipeline().analyze(Step1Input(
        text="My mother has severe osteoarthritis of both knees, surgeon recommended knee replacement", debug=True))
    assert result["decision"] == "majority"
    assert result["suggested_specialty"] == "Orthopaedics"
    assert "knee replacement" in result["evidence"]
    assert result["suggested_specialty_label"] == "Suggested speciality to search: Orthopaedics"
    assert len(result["debug"]["agreeing_voters"]) >= 2


def test_invented_evidence_is_dropped_and_leads_to_clarification():
    result = make_pipeline().analyze(Step1Input(text="invented message with no medical words", debug=True))
    assert result["decision"] == "clarification_required"
    assert result["evidence"] == []
    assert [f["name"] for f in result["clarification"]["fields"]] == ["body_area", "existing_diagnosis", "recommended_procedure"]


def test_after_two_rounds_the_user_picks_from_the_list():
    result = make_pipeline().analyze(Step1Input(text="invented", clarification_round=2))
    assert result["decision"] == "needs_user_choice"
    assert "Orthopaedics" in result["user_choice"]["options"]


def test_general_medicine_majority_asks_once_then_accepts():
    first = make_pipeline().analyze(Step1Input(text="weakness"))
    assert first["decision"] == "clarification_required"
    second = make_pipeline().analyze(Step1Input(text="weakness", clarification_round=1,
                                                 clarification={"body_area": "Other / not sure"}))
    assert second["decision"] == "majority" and second["suggested_specialty"] == "General Medicine"


def test_general_medicine_only_wins_a_search_voter_when_no_specialist_matched():
    from mediroute.specialty_routing.step1.voters import KeywordVoter
    index = LookupIndex(ENTRIES, encoder=FakeEncoder(), cache=False)
    assert KeywordVoter(index).vote(["weakness"]).top1 == "General Medicine"
    assert KeywordVoter(index).vote(["weakness", "osteoarthritis of knee"]).top1 == "Orthopaedics"


def test_general_symptom_is_not_pulled_to_a_specialist_by_a_partial_lay_term():
    """'weakness' must stay General Medicine even though the lay term 'weakness in arm' is Neurology."""
    from mediroute.specialty_routing.step1.voters import KeywordVoter
    entries = ENTRIES + [LookupEntry("lay:gm", "lay_term", "", "weakness", "General Medicine"),
                         LookupEntry("lay:neuro", "lay_term", "", "weakness in arm", "Neurology")]
    index = LookupIndex(entries, encoder=FakeEncoder(), cache=False)
    assert KeywordVoter(index).vote(["weakness"]).top1 == "General Medicine"
    assert KeywordVoter(index).vote(["weakness in arm"]).top1 == "Neurology"


def test_user_selected_specialty_is_returned():
    result = make_pipeline().analyze(Step1Input(text="anything", selected_specialty="Ophthalmology", clarification_round=2))
    assert result["decision"] == "user_selected" and result["suggested_specialty"] == "Ophthalmology"


def test_llm_down_falls_back_to_rule_evidence_and_search_voters():
    result = make_pipeline(down=True).analyze(Step1Input(text="need cabg bypass surgery for my father", debug=True))
    assert result["debug"]["votes"]["V3"]["ok"] is False
    assert result["suggested_specialty"] == "Cardiothoracic Surgery"  # V1 + V2 still agree


def test_every_stage_is_traced_with_one_request_id():
    result = make_pipeline().analyze(Step1Input(text="osteoarthritis of the knee, knee replacement", debug=True))
    stages = result["debug"]["trace_events"]
    for stage in ["input", "emergency_check", "llm_call", "evidence", "vote", "votes_summary", "decision"]:
        assert stage in stages
    assert len(result["request_id"]) == 12
