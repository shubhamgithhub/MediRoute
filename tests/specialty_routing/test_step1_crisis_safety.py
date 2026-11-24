"""23 Nov: crisis safety. The live request "commiting sucide" got no crisis message: the rule only knew
the exact spelling. Now: misspellings of suicide words, acute intent -> Emergency Medicine, and the
evidence LLM's self-harm quote as a second net (it can add the crisis message, never remove one)."""

from __future__ import annotations

import csv
import glob
from pathlib import Path

import pytest

from mediroute.specialty_routing.step1 import safety
from mediroute.specialty_routing.step1.evidence import EvidenceExtractor, evidence_schema
from mediroute.specialty_routing.step1.lookup import LookupIndex
from mediroute.specialty_routing.step1.ollama_client import LLMCall
from mediroute.specialty_routing.step1.pipeline import Step1Input, Step1Pipeline
from mediroute.specialty_routing.step1.safety import add_llm_self_harm, check_emergency, routes_to_emergency
from mediroute.specialty_routing.step1.voters import LLMVoter
from tests.specialty_routing.test_step1_pipeline import ENTRIES, FakeEncoder

ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------- rules (stage 2)
@pytest.mark.parametrize("text", [
    "commiting sucide",                       # the live request of 23 Nov
    "mar jaana chahta hoon",                  # Hinglish (safety set S04)
    "jeene ka mann nahi karta",
    "sucidal thoughts since last month",
    "I keep thinking about suicde",
    "i want to kil mysef",
    "I don't want to live anymore",
    "thoughts of self harm",
])
def test_suicidal_words_get_the_crisis_message_even_misspelt(text):
    result = check_emergency(text)
    assert result["is_emergency"] and "Tele-MANAS" in result["message"]


@pytest.mark.parametrize("text", [
    "commiting sucide",
    "I am going to kill myself tonight",
    "I will take all my pills, I want to die",
    "I am planning to end my life",
])
def test_acute_intent_routes_to_emergency_with_both_messages(text):
    result = check_emergency(text)
    assert routes_to_emergency(result) and "suicidal_acute" in result["matched_rules"]
    assert "emergency" in result["message"].lower() and "Tele-MANAS" in result["message"]


@pytest.mark.parametrize("text", [
    "I have had suicidal thoughts for years and want to see a psychiatrist",
    "I am thinking about suicide, going to see a psychiatrist next week",
])
def test_thoughts_alone_keep_psychiatry_routing_with_the_crisis_message(text):
    result = check_emergency(text)
    assert result["is_emergency"] and not routes_to_emergency(result)
    assert result["message"] == safety.CRISIS_MESSAGE


@pytest.mark.parametrize("text", [
    "I hurt myself playing cricket and my knee is swollen",
    "I decided to get a knee replacement",
    "eating spicy food gives me heartburn",
    "I was bending and my back started hurting",
])
def test_no_false_crisis_or_red_flag(text):
    assert not check_emergency(text)["is_emergency"]


def test_spelling_correction_adds_nothing_on_the_gold_sets():
    """Every gold message: the rules give the same result with and without the corrected copy."""
    plain = [(name, [re for re in patterns]) for name, patterns in safety._COMPILED]
    checked = 0
    for path in glob.glob(str(ROOT / "data" / "evaluation" / "step*_gold*.csv")):
        with open(path, encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                text = row.get("query") or row.get("patient_text") or row.get("text") or ""
                if not text:
                    continue
                checked += 1
                as_written = [n for n, ps in plain if all(p.search(text) for p in ps)]
                assert check_emergency(text)["matched_rules"] == as_written, text
    assert checked > 300


# ---------------------------------------------------------------- LLM quote (stage 3a)
def test_llm_quote_adds_the_crisis_message_and_never_removes_one():
    words = "everyone would be better off without me"          # no rule reads this; the LLM can
    missed = check_emergency(words)
    assert not missed["is_emergency"]
    added = add_llm_self_harm(missed, words, words)
    assert added["is_emergency"] and added["matched_rules"] == ["self_harm_llm"] and not routes_to_emergency(added)
    assert add_llm_self_harm(missed, "", words) is missed                                 # no quote: unchanged
    caught = check_emergency("I want to die")
    assert add_llm_self_harm(caught, "", "I want to die") is caught                       # rule result kept
    acute = add_llm_self_harm(missed, words, words + ", I have the pills ready")
    assert routes_to_emergency(acute)


def test_evidence_schema_asks_for_the_self_harm_quote():
    schema = evidence_schema()
    assert schema["properties"]["self_harm"] == {"type": "string"} and "self_harm" in schema["required"]


# ---------------------------------------------------------------- pipeline
class CrisisClient:
    """Evidence replies with a self-harm quote; the LLM voter answers Psychiatry."""

    model = "fake-llm"
    QUOTES = {"better off": "everyone would be better off without me", "invented": "I want to kill myself"}

    def warm_up(self) -> None:
        pass

    def generate_json(self, prompt: str, schema: dict, purpose: str) -> LLMCall:
        message = prompt.rsplit("Patient message:", 1)[-1].lower()
        if purpose == "evidence_extraction":
            quote = next((q for key, q in self.QUOTES.items() if key in message), "")
            return LLMCall(True, parsed={"conditions": ["feeling very low"], "procedures": [], "body_parts": [],
                                         "named_diagnoses": [], "symptom_areas": [], "self_harm": quote},
                           details={"purpose": purpose})
        return LLMCall(True, parsed={"specialty": "Psychiatry", "alternatives": [], "evidence_terms": []},
                       details={"purpose": purpose})


def make_pipeline() -> Step1Pipeline:
    from mediroute.specialty_routing.step1.judge import LLMJudge
    from mediroute.specialty_routing.step1.ollama_client import DisabledLLMClient
    client = CrisisClient()
    index = LookupIndex(ENTRIES, encoder=FakeEncoder(), cache=False)
    return Step1Pipeline(index=index, client=client, extractor=EvidenceExtractor(client), llm_voter=LLMVoter(client),
                         judge=LLMJudge(client=DisabledLLMClient(), index=index))


def test_pipeline_live_case_goes_to_emergency_without_the_llm():
    out = make_pipeline().analyze(Step1Input(text="commiting sucide"))
    assert out["decision"] == "emergency_rule" and out["suggested_specialty"] == "Emergency Medicine"
    assert "Tele-MANAS" in out["emergency_message"]


def test_pipeline_llm_quote_adds_crisis_message_the_rules_missed():
    out = make_pipeline().analyze(Step1Input(text="feeling very low, everyone would be better off without me"))
    assert out["emergency"] and "Tele-MANAS" in out["emergency_message"]
    assert out["decision"] != "emergency_rule"                           # thoughts: normal routing continues


def test_pipeline_llm_quote_with_acute_words_goes_to_emergency():
    out = make_pipeline().analyze(Step1Input(text="feeling very low, everyone would be better off without me, the pills are ready"))
    assert out["decision"] == "emergency_rule" and out["suggested_specialty"] == "Emergency Medicine"


def test_pipeline_ignores_a_quote_that_is_not_in_the_text():
    out = make_pipeline().analyze(Step1Input(text="feeling very low, invented words"))
    assert not out["emergency"]
