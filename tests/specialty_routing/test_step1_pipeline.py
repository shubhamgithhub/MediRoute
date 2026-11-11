"""Step 1 voting pipeline, tested without Ollama or the embedding model (both faked)."""

from __future__ import annotations

import re

import numpy as np
import pytest

from mediroute.specialty_routing.step1.evidence import EvidenceExtractor, verify_phrase
from mediroute.specialty_routing.step1.lookup import LookupEntry, LookupIndex
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


class FakeJudgeClient:
    """Answers the judge prompt with a fixed reply (or fails). Never calls a network."""

    model = "fake-judge"

    def __init__(self, reply: dict | None = None, ok: bool = True) -> None:
        self.reply, self.ok, self.prompts = reply or {}, ok, []

    def generate_json(self, prompt: str, schema: dict, purpose: str) -> LLMCall:
        self.prompts.append(prompt)
        if not self.ok:
            return LLMCall(False, error="HTTP 429: rate limited", details={"purpose": purpose})
        return LLMCall(True, parsed=dict(self.reply), raw_response=str(self.reply), details={"purpose": purpose})


def make_pipeline(down: bool = False, specialty: dict | None = None, judge_client=None) -> Step1Pipeline:
    from mediroute.specialty_routing.step1.judge import LLMJudge
    from mediroute.specialty_routing.step1.ollama_client import DisabledLLMClient
    client = FakeClient(EVIDENCE, specialty or SPECIALTY, down=down)
    index = LookupIndex(ENTRIES, encoder=FakeEncoder(), cache=False)
    judge = LLMJudge(client=judge_client or DisabledLLMClient(), index=index)
    return Step1Pipeline(index=index, client=client, extractor=EvidenceExtractor(client), llm_voter=LLMVoter(client),
                         judge=judge)


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
    from collections import Counter

    from mediroute.specialty_routing.step1.lookup import _lay_term_entries
    lay = {(e.text, e.specialty, e.evidence_type) for e in _lay_term_entries(set(), Counter())}
    assert ("eye infection", "Ophthalmology", "strong") in lay
    assert ("baby", "Paediatrics", "weak") in lay
    # a lay term already present as official text is not copied again
    assert not any(t == "asthma" for t, _, _ in {(e.text, e.specialty, e.evidence_type)
                                                 for e in _lay_term_entries({"asthma"}, Counter())})


@pytest.fixture(scope="module")
def built_lookup():
    """The generated lookup in data/processed (rebuild: python -m mediroute.data_generator.rebuild)."""
    from mediroute.specialty_routing.step1.lookup import load_lookup
    rows: dict[str, set] = {}
    for e in load_lookup():
        rows.setdefault(e.code or e.text, set()).add((e.specialty, e.evidence_type, e.mapping_rule))
    return rows


@pytest.mark.parametrize("code, specialty, evidence_type, rule", [
    ("N200", "Urology", "diagnosis", "ccsr:GEN005"),      # calculus of kidney
    ("R070", "ENT", "symptom", "ccsr:SYM013"),            # pain in throat: no longer Cardiology
    ("M545", "Orthopaedics", "symptom", "ccsr:MUS038"),   # low back pain counts as a symptom
])
def test_icd_codes_reach_specialities_through_ccsr(built_lookup, code, specialty, evidence_type, rule):
    assert (specialty, evidence_type, rule) in built_lookup[code]


def test_known_mapping_errors_are_gone(built_lookup):
    assert not any(s == "Cardiology" for s, _, _ in built_lookup["R070"])          # throat pain
    assert not any(s == "Orthopaedics" for s, _, _ in built_lookup.get("S370", set()))  # kidney injury
    assert "R07" not in built_lookup  # "Pain in throat and chest": sub-codes differ, header left out


def test_weak_evidence_counts_half():
    from mediroute.specialty_routing.step1.voters import _aggregate
    strong = LookupEntry("a", "icd10cm", "N200", "Calculus of kidney", "Urology", "diagnosis")
    symptom = LookupEntry("b", "icd10cm", "M545", "Low back pain", "Orthopaedics", "symptom")
    top3, _ = _aggregate([("kidney stone", [(strong, 0.6)]), ("back pain", [(symptom, 0.8)])], 0.25)
    assert top3[0][0] == "Urology"  # 0.6 beats 0.8 x 0.5


# ---------------------------------------------------------------- decisions
def test_agreeing_voters_select_the_specialty():
    result = make_pipeline().analyze(Step1Input(
        text="My mother has severe osteoarthritis of both knees, surgeon recommended knee replacement", debug=True))
    assert result["decision"] == "agreement"
    assert result["suggested_specialty"] == "Orthopaedics"
    assert "knee replacement" in result["evidence"]
    assert result["suggested_specialty_label"] == "Suggested speciality to search: Orthopaedics"
    assert result["debug"]["agreeing_voters"] == ["V1", "V2"]


def test_invented_evidence_is_dropped_and_leads_to_clarification():
    result = make_pipeline().analyze(Step1Input(text="invented message with no medical words", debug=True))
    assert result["decision"] == "clarification_required"
    assert result["evidence"] == []
    assert [f["name"] for f in result["clarification"]["fields"]] == ["body_area", "existing_diagnosis", "recommended_procedure"]


def test_after_two_rounds_the_user_picks_from_the_list():
    result = make_pipeline().analyze(Step1Input(text="invented", clarification_round=2))
    assert result["decision"] == "needs_user_choice"
    assert "Orthopaedics" in result["user_choice"]["options"]


def test_general_medicine_answer_asks_once_then_accepts():
    first = make_pipeline().analyze(Step1Input(text="weakness"))
    assert first["decision"] == "clarification_required"
    second = make_pipeline().analyze(Step1Input(text="weakness", clarification_round=1,
                                                 clarification={"body_area": "Other / not sure"}))
    assert second["decision"] == "agreement" and second["suggested_specialty"] == "General Medicine"


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
    assert result["debug"]["votes"]["V2"]["ok"] is False
    assert result["decision"] == "lookup_only" and result["suggested_specialty"] == "Cardiothoracic Surgery"


def test_every_stage_is_traced_with_one_request_id():
    result = make_pipeline().analyze(Step1Input(text="osteoarthritis of the knee, knee replacement", debug=True))
    stages = result["debug"]["trace_events"]
    for stage in ["input", "emergency_check", "llm_call", "evidence", "vote", "votes_summary", "decision"]:
        assert stage in stages
    assert len(result["request_id"]) == 12


# ---------------------------------------------------------------- running without an LLM
def test_llm_turned_off_still_routes_with_search_voters_and_shows_a_notice():
    from mediroute.specialty_routing.step1.ollama_client import DisabledLLMClient
    client = DisabledLLMClient()
    index = LookupIndex(ENTRIES, encoder=FakeEncoder(), cache=False)
    pipeline = Step1Pipeline(index=index, client=client, extractor=EvidenceExtractor(client),
                             llm_voter=LLMVoter(client))
    pipeline.warm_up(__import__("logging").getLogger("test"))  # must not raise
    result = pipeline.analyze(Step1Input(text="need cabg bypass surgery for my father", debug=True))
    assert result["suggested_specialty"] == "Cardiothoracic Surgery"  # the lookup voter answers alone
    assert result["llm_available"] is False and "not available" in result["notice"]
    assert result["debug"]["votes"]["V2"]["ok"] is False


def test_unreachable_ollama_is_detected_once_and_later_calls_are_skipped_instantly():
    import time
    from mediroute.specialty_routing.step1.ollama_client import OllamaClient
    client = OllamaClient(base_url="http://127.0.0.1:9")  # nothing listens on port 9
    assert client.status()["available"] is False
    start = time.perf_counter()
    call = client.generate_json("x", {}, purpose="evidence_extraction")
    assert not call.ok and call.details.get("skipped") and "LLM unavailable" in call.error
    assert time.perf_counter() - start < 0.1


def test_llm_provider_switch(monkeypatch):
    from mediroute.specialty_routing.step1.ollama_client import DisabledLLMClient, OllamaClient, make_llm_client
    monkeypatch.setenv("MEDIROUTE_LLM_PROVIDER", "none")
    assert isinstance(make_llm_client(), DisabledLLMClient)
    monkeypatch.setenv("MEDIROUTE_LLM_PROVIDER", "ollama")
    assert isinstance(make_llm_client(), OllamaClient)
    monkeypatch.setenv("MEDIROUTE_LLM_PROVIDER", "gpt-without-code")
    with pytest.raises(ValueError):
        make_llm_client()


# ---------------------------------------------------------------- OpenRouter (no network: _request is faked)
def test_openrouter_without_key_is_skipped_with_a_clear_reason():
    from mediroute.specialty_routing.step1.ollama_client import OpenRouterClient
    client = OpenRouterClient(api_key="")
    assert client.status()["available"] is False and "OPENROUTER_API_KEY" in client.status()["reason"]
    call = client.generate_json("x", {}, purpose="specialty_vote")
    assert not call.ok and call.details["skipped"]


def test_openrouter_parses_json_even_inside_a_code_fence(monkeypatch):
    from mediroute.specialty_routing.step1.ollama_client import OpenRouterClient
    client = OpenRouterClient(api_key="sk-or-test", model="some/model:free")
    fence = "`" * 3
    body = {"id": "gen-1", "model": "some/model:free", "provider": "X", "first_token_ms": 400, "reasoning_chars": 0,
            "usage": {"prompt_tokens": 50, "completion_tokens": 9, "completion_tokens_details": {"reasoning_tokens": 0}},
            "content": fence + 'json\n{"specialty": "Ophthalmology"}\n' + fence}
    sent = {}
    monkeypatch.setattr(client, "_stream_chat", lambda payload: sent.update(payload) or body)
    call = client.generate_json("eye infection", {"type": "object"}, purpose="specialty_vote")
    assert call.ok and call.parsed == {"specialty": "Ophthalmology"}
    assert call.details["prompt_tokens"] == 50 and call.details["upstream_provider"] == "X"
    assert call.details["first_token_ms"] == 400 and call.details["reasoning_tokens"] == 0
    assert sent["reasoning"] == {"enabled": False}  # hidden reasoning is off by default


def test_openrouter_rate_limit_marks_it_down_so_next_calls_skip(monkeypatch):
    import io
    import urllib.error
    from mediroute.specialty_routing.step1.ollama_client import OpenRouterClient
    client = OpenRouterClient(api_key="sk-or-test")

    def limited(payload):
        raise urllib.error.HTTPError("x", 429, "Too Many Requests", {}, io.BytesIO(b'{"error":"free-models-per-day"}'))
    monkeypatch.setattr(client, "_stream_chat", limited)
    first = client.generate_json("x", {}, purpose="specialty_vote")
    assert not first.ok and "429" in first.error
    second = client.generate_json("x", {}, purpose="specialty_vote")
    assert second.details.get("skipped") and client.status()["available"] is False


def test_hosted_llm_runs_v3_in_parallel_with_the_same_result():
    class ParallelFake(FakeClient):
        parallel_calls = True
    client = ParallelFake(EVIDENCE, SPECIALTY)
    index = LookupIndex(ENTRIES, encoder=FakeEncoder(), cache=False)
    pipeline = Step1Pipeline(index=index, client=client, extractor=EvidenceExtractor(client), llm_voter=LLMVoter(client))
    result = pipeline.analyze(Step1Input(text="osteoarthritis of the knee, knee replacement", debug=True))
    assert result["suggested_specialty"] == "Orthopaedics"
    assert result["debug"]["votes"]["V2"]["top3"][0][0] == "Orthopaedics"


def test_openrouter_falls_back_to_the_next_free_model_when_one_is_busy(monkeypatch):
    from mediroute.specialty_routing.step1.ollama_client import OpenRouterClient, _ProviderError
    client = OpenRouterClient(api_key="sk-or-test", model="busy/model:free, good/model:free")
    asked = []

    def stream(payload):
        asked.append(payload["model"])
        if payload["model"] == "busy/model:free":
            raise _ProviderError(429, "busy/model:free is temporarily rate-limited upstream")
        return {"content": '{"specialty": "Cardiology"}', "usage": {}, "first_token_ms": 300, "model": payload["model"]}
    monkeypatch.setattr(client, "_stream_chat", stream)
    first = client.generate_json("x", {}, purpose="specialty_vote")
    assert first.ok and first.details["model"] == "good/model:free"
    assert first.details["models_tried"][0]["model"] == "busy/model:free"
    second = client.generate_json("x", {}, purpose="specialty_vote")
    assert second.ok and asked == ["busy/model:free", "good/model:free", "good/model:free"]  # busy one skipped
    assert client.status()["available"] is True  # a busy model doesn't take the whole LLM down


# ---------------------------------------------------------------- the LLM judge
DISAGREE = {**SPECIALTY, "cabg": "Cardiology"}  # the LLM voter says Cardiology, the lookup Cardiothoracic Surgery


def test_disagreement_is_settled_by_the_judge_when_its_answer_passes_the_checks():
    reply = {"choice": "Cardiothoracic Surgery", "evidence": ["E1"], "patient_quote": "cabg",
             "reason": "A planned bypass operation is cardiothoracic surgery."}
    judge = FakeJudgeClient(reply)
    result = make_pipeline(specialty=DISAGREE, judge_client=judge).analyze(
        Step1Input(text="need cabg bypass surgery for my father", debug=True))
    assert result["decision"] == "judge" and result["suggested_specialty"] == "Cardiothoracic Surgery"
    assert len(judge.prompts) == 2  # asked twice, candidates in both orders
    assert "judge" in result["debug"]["trace_events"]


@pytest.mark.parametrize("reply, ok", [
    ({"choice": "Cardiology", "evidence": ["E9"], "patient_quote": "cabg", "reason": ""}, True),  # invented evidence
    ({"choice": "Cardiothoracic Surgery", "evidence": ["E1"], "patient_quote": "chest pain", "reason": ""}, True),  # quote not in text
    ({"choice": "unclear", "evidence": [], "patient_quote": "", "reason": ""}, True),
    ({}, False),  # rate limited / error
])
def test_a_judge_answer_that_fails_a_check_leads_to_a_question(reply, ok):
    result = make_pipeline(specialty=DISAGREE, judge_client=FakeJudgeClient(reply, ok=ok)).analyze(
        Step1Input(text="need cabg bypass surgery for my father"))
    assert result["decision"] == "clarification_required" and result["suggested_specialty"] is None


def test_without_a_judge_a_disagreement_asks_the_patient():
    result = make_pipeline(specialty=DISAGREE).analyze(Step1Input(text="need cabg bypass surgery for my father"))
    assert result["decision"] == "clarification_required"
    assert "Cardiothoracic Surgery" in result["reason"] and "Cardiology" in result["reason"]


def test_llm_answering_unclear_asks_instead_of_letting_the_lookup_guess():
    """The LLM read the message and said "Unclear": ask. Only an unavailable LLM lets the lookup answer alone."""
    vague = {**SPECIALTY}
    vague.pop("osteoarthritis")  # the fake LLM answers Unclear for this message
    result = make_pipeline(specialty=vague).analyze(Step1Input(text="osteoarthritis of the knee, knee replacement"))
    assert result["decision"] == "clarification_required" and result["suggested_specialty"] is None
    assert "too general" in result["reason"]
    down = make_pipeline(down=True).analyze(Step1Input(text="osteoarthritis of the knee, knee replacement"))
    assert down["decision"] == "lookup_only" and down["suggested_specialty"] == "Orthopaedics"


@pytest.mark.parametrize("phrase, searched", [
    ("Problem in my stomach", "stomach"),
    ("severe pain on one side of back", "severe pain one side back"),
    ("treatment", "treatment"),  # nothing left: searched unchanged (and dropped earlier as generic)
])
def test_generic_words_are_not_searched(phrase, searched):
    from mediroute.specialty_routing.step1.evidence import search_text
    assert search_text(phrase) == searched


def test_weak_hits_on_several_phrases_do_not_outweigh_one_clear_match():
    """C044: "problem in my stomach" + "problem in my head" both weakly matched "heart problem" (Cardiology)."""
    from mediroute.specialty_routing.step1.voters import _aggregate
    stomach = LookupEntry("a", "lay_term", "", "stomach pain", "Gastroenterology", "strong")
    heart = LookupEntry("b", "lay_term", "", "heart problem", "Cardiology", "strong")
    per_phrase = [("problem in my stomach", [(stomach, 0.032), (heart, 0.016)]),
                  ("problem in my head", [(heart, 0.017)])]
    assert _aggregate(per_phrase, 0.0)[0][0][0] == "Cardiology"                  # summing: weak hits win
    assert _aggregate(per_phrase, 0.0, best_only=True)[0][0][0] == "Gastroenterology"  # best match per phrase
