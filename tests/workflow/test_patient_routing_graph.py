"""Patient-routing graph (Step 1 + Step 2) with fake Step 1 and Step 2, so it runs in seconds.

Scenarios follow Shubham's Step 12 tests (graph, decisions, 12E-12G), adapted to the integrated
graph where the medical step is the Step 1 voting pipeline.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mediroute.backend.workflow.patient_routing_graph import PatientRoutingGraph
from mediroute.backend.workflow.routing_decisions import (
    decide_after_recommendation,
    decide_after_report_parsing,
    decide_after_step1,
)
from mediroute.backend.workflow.routing_nodes import RoutingNodes

REPORTS = Path(__file__).resolve().parents[2] / "data" / "raw" / "test_reports"


def step1_result(decision: str, specialty: str | None, **extra) -> dict:
    return {"request_id": "rid123", "parent_request_id": None, "decision": decision,
            "suggested_specialty": specialty, "suggested_specialty_label": None, "care_category": None,
            "in_hospital_data": True, "evidence": ["x"], "reason": f"{decision} reason",
            "evidence_detail": {"conditions": ["coronary artery disease"], "procedures": ["CABG"],
                                "body_parts": [], "keyword_matches": []},
            "emergency": False, "emergency_message": None, "clarification_required": decision == "clarification_required",
            "clarification": None, "user_choice": None, "disclaimer": "d", "latency_ms": 1, **extra}


class FakePipeline:
    def __init__(self):
        self.calls = []

    def analyze(self, inp):
        self.calls.append(inp)
        text = (inp.text + " " + inp.report_text).lower()
        if inp.selected_specialty:
            return step1_result("user_selected", inp.selected_specialty)
        if "coronary" in text or "cabg" in text or "atrial fibrillation" in text:
            return step1_result("majority", "Cardiology")
        if "cataract" in text:
            return step1_result("majority", "Ophthalmology")
        return step1_result("clarification_required", None)


class FakeService:
    def __init__(self):
        self.pipeline = FakePipeline()


class FakeEngine:
    def __init__(self):
        self.contexts = []

    def recommend(self, context, preferred_city=None, preferred_state=None, top_k=5):
        self.contexts.append(context)
        if context.primary_specialty == "Ophthalmology":
            return {"status": "no_specialty_match", "primary_specialty": "Ophthalmology", "count": 0, "results": []}
        if preferred_city == "Nowhere":
            return {"status": "no_location_match", "primary_specialty": context.primary_specialty, "count": 0, "results": []}
        return {"status": "success", "primary_specialty": context.primary_specialty, "count": 2,
                "results": [{"hospital_name": "H1"}, {"hospital_name": "H2"}]}


def run(requirement="", reports=(), city=None, **extra):
    service, engine = FakeService(), FakeEngine()
    graph = PatientRoutingGraph(RoutingNodes(step1_service=service, recommendation_engine=engine))
    state = {"workflow_id": "wf-test", "patient_request": {"requirement": requirement},
             "report_files": [{"filename": p.name, "content": p.read_bytes()} for p in reports],
             "preferred_city": city, "top_k": 5, **extra}
    return graph.invoke(state), service, engine


# ---------------------------------------------------------------- decisions
def test_decisions():
    assert decide_after_report_parsing({"patient_request": {"requirement": "knee pain"}}) == "route"
    assert decide_after_report_parsing({"patient_request": {"requirement": ""}, "report_text": "ECG ..."}) == "route"
    assert decide_after_report_parsing({"patient_request": {"requirement": ""}, "report_text": ""}) == "clarify"
    assert decide_after_step1({"routing_ready": True}) == "recommend"
    assert decide_after_step1({"routing_ready": False}) == "clarify"
    assert decide_after_step1({"error_message": "x"}) == "error"
    assert decide_after_recommendation({"recommendation_result": {"status": "success"}}) == "finish"
    assert decide_after_recommendation({"recommendation_result": {"status": "no_location_match"}}) == "clarify_location"
    assert decide_after_recommendation({"recommendation_result": {"status": "no_specialty_match"}}) == "no_hospital"
    assert decide_after_recommendation({"recommendation_result": {}}) == "error"


# ---------------------------------------------------------------- graph paths
def test_text_only_routes_to_hospitals():
    result, _, engine = run("Doctor advised CABG for my father", city="Chennai")
    assert result["workflow_status"] == "completed"
    assert result["step1_result"]["suggested_specialty"] == "Cardiology"
    assert engine.contexts[0].primary_specialty == "Cardiology"
    assert engine.contexts[0].procedures == ["CABG"]  # Step 1 evidence reaches Step 2
    assert result["recommendation_result"]["count"] == 2


def test_report_only_routes_to_hospitals():
    result, service, _ = run("", reports=[REPORTS / "MediRoute_Report_01_Coronary_Artery_Disease.pdf"])
    assert result["parse_summary"]["successful_files"] == 1
    assert "Coronary" in service.pipeline.calls[0].report_text
    assert result["workflow_status"] == "completed"


def test_step1_clarification_ends_in_medical_clarification():
    result, _, engine = run("weakness")
    assert result["clarification_type"] == "medical"
    assert result["workflow_status"] == "waiting_for_clarification"
    assert engine.contexts == []  # Step 2 never runs without a speciality


def test_nothing_to_analyse_asks_for_text_or_report():
    result, service, _ = run("", reports=[REPORTS / "MediRoute_Blank_Test.pdf"])
    assert result["clarification_type"] == "report"
    assert service.pipeline.calls == []


def test_no_hospital_in_city_asks_about_location():
    result, _, _ = run("CABG", city="Nowhere")
    assert result["clarification_type"] == "location"


def test_specialty_without_verified_hospital_ends_with_message():
    result, _, _ = run("cataract in both eyes")
    assert result["workflow_status"] == "no_hospital_for_specialty"
    assert "Ophthalmology" in result["clarification_reason"]


def test_user_selected_specialty_flows_to_step2():
    result, _, engine = run("I need surgery", selected_specialty="Cardiology", clarification_round=2)
    assert result["step1_result"]["decision"] == "user_selected"
    assert engine.contexts[0].primary_specialty == "Cardiology"


@pytest.mark.parametrize("pdf", ["11_abnormal_MR-SYN-203.pdf", "MediRoute_Report_02_Heart_Failure.pdf"])
def test_shubham_synthetic_reports_parse(pdf):
    result, service, _ = run("", reports=[REPORTS / pdf])
    assert result["parse_summary"]["overall_status"] == "success"
    assert service.pipeline.calls and service.pipeline.calls[0].report_text
