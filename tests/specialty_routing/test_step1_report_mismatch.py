"""24 Nov: typed text vs attached report. A knee report attached to "chest tightness when I climb
stairs" must not steer the answer: when the two point to specialities with nothing in common, the
typed text decides and the patient is told. A report that supports the text, or a vague text such as
"report attached", works as before."""

from __future__ import annotations

from mediroute.specialty_routing.step1.evidence import EvidenceExtractor
from mediroute.specialty_routing.step1.judge import LLMJudge
from mediroute.specialty_routing.step1.lookup import LookupIndex
from mediroute.specialty_routing.step1.ollama_client import DisabledLLMClient, LLMCall
from mediroute.specialty_routing.step1.pipeline import Step1Input, Step1Pipeline
from mediroute.specialty_routing.step1.voters import LLMVoter
from tests.specialty_routing.test_step1_pipeline import ENTRIES, FakeEncoder

KNEE_REPORT = "Preoperative examination before total knee replacement. Osteoarthritis of knee, varus deformity."


class ReportClient:
    """Evidence: the phrases below that appear in the message. AI vote: Orthopaedics whenever the
    message mentions the knee (the report steering it), else Cardiology for the heart."""

    model = "fake-llm"
    PHRASES = {"conditions": ["chest tightness", "osteoarthritis of knee", "chronic ischemic heart disease"],
               "procedures": ["total knee replacement"], "body_parts": ["knee", "chest"]}

    def warm_up(self) -> None:
        pass

    def generate_json(self, prompt: str, schema: dict, purpose: str) -> LLMCall:
        message = prompt.rsplit("Patient message:", 1)[-1].lower()
        if purpose == "evidence_extraction":
            found = {k: [p for p in v if p in message] for k, v in self.PHRASES.items()}
            return LLMCall(True, parsed={**found, "named_diagnoses": [], "symptom_areas": [], "self_harm": ""},
                           details={"purpose": purpose})
        pick = "Orthopaedics" if "knee" in message else "Cardiology" if ("chest" in message or "heart" in message) else "Unclear"
        return LLMCall(True, parsed={"specialty": pick, "alternatives": [], "evidence_terms": []},
                       details={"purpose": purpose})


def make_pipeline() -> Step1Pipeline:
    client = ReportClient()
    index = LookupIndex(ENTRIES, encoder=FakeEncoder(), cache=False)
    return Step1Pipeline(index=index, client=client, extractor=EvidenceExtractor(client), llm_voter=LLMVoter(client),
                         judge=LLMJudge(client=DisabledLLMClient(), index=index))


def test_report_about_another_problem_does_not_steer_the_answer():
    out = make_pipeline().analyze(Step1Input(text="chest tightness, chronic ischemic heart disease",
                                             report_text=KNEE_REPORT))
    assert out["suggested_specialty"] == "Cardiology"
    assert out["report_notice"] and "Orthopaedics" in out["report_notice"] and "Cardiology" in out["report_notice"]
    kept = sum(out["evidence_detail"].values(), [])
    assert not any("knee" in p for p in kept)                      # Step 2 gets only the typed text's words


def test_report_that_supports_the_text_is_used_without_a_notice():
    out = make_pipeline().analyze(Step1Input(text="knee pain, I need a total knee replacement",
                                             report_text=KNEE_REPORT))
    assert out["suggested_specialty"] == "Orthopaedics" and out["report_notice"] is None
    assert "osteoarthritis of knee" in sum(out["evidence_detail"].values(), [])


def test_vague_text_lets_the_report_decide_as_before():
    out = make_pipeline().analyze(Step1Input(text="My scan report is attached.", report_text=KNEE_REPORT))
    assert out["suggested_specialty"] == "Orthopaedics" and out["report_notice"] is None


def test_no_report_no_check():
    out = make_pipeline().analyze(Step1Input(text="chest tightness, chronic ischemic heart disease"))
    assert out["suggested_specialty"] == "Cardiology" and out["report_notice"] is None
