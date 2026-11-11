"""The patient-routing graph (LangGraph): reports -> Step 1 -> Step 2 -> result or clarification.

Ported from Shubham's patient_routing_graph.py (Step 12). Same shape; the two medical nodes
(extract_medical_context, validate_medical_context) are replaced by one ``step1_route`` node:

    START -> parse_reports -> step1_route -> recommend_hospitals -> finalize -> END
                 |               |                 |-> location_clarification -> END
                 |               |                 |-> no_hospital_for_specialty -> END
                 |               |                 '-> medical_clarification -> END
                 '-> clarification (nothing to analyse)
                                 '-> medical_clarification (Step 1 asks / offers the list)
    any node -> error -> END
"""

from langgraph.graph import END, START, StateGraph

from mediroute.backend.workflow.routing_decisions import (
    decide_after_recommendation,
    decide_after_report_parsing,
    decide_after_step1,
)
from mediroute.backend.workflow.routing_nodes import RoutingNodes
from mediroute.backend.workflow.routing_state import PatientRoutingState


class PatientRoutingGraph:
    def __init__(self, nodes: RoutingNodes | None = None) -> None:
        self.nodes = nodes or RoutingNodes()
        self.graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(PatientRoutingState)

        builder.add_node("parse_reports", self.nodes.parse_reports)
        builder.add_node("step1_route", self.nodes.step1_route)
        builder.add_node("recommend_hospitals", self.nodes.recommend_hospitals)
        builder.add_node("medical_clarification", self.nodes.create_clarification)
        builder.add_node("location_clarification", self.nodes.create_location_clarification)
        builder.add_node("no_hospital_for_specialty", self.nodes.no_hospital_for_specialty)
        builder.add_node("finalize", self.nodes.finalize)
        builder.add_node("error", self.nodes.handle_error)

        builder.add_edge(START, "parse_reports")
        builder.add_conditional_edges("parse_reports", decide_after_report_parsing, {
            "route": "step1_route",
            "clarify": "medical_clarification",
            "error": "error",
        })
        builder.add_conditional_edges("step1_route", decide_after_step1, {
            "recommend": "recommend_hospitals",
            "clarify": "medical_clarification",
            "error": "error",
        })
        builder.add_conditional_edges("recommend_hospitals", decide_after_recommendation, {
            "finish": "finalize",
            "clarify_location": "location_clarification",
            "no_hospital": "no_hospital_for_specialty",
            "clarify_medical": "medical_clarification",
            "error": "error",
        })
        for node in ("medical_clarification", "location_clarification", "no_hospital_for_specialty",
                     "finalize", "error"):
            builder.add_edge(node, END)
        return builder.compile()

    def invoke(self, state: PatientRoutingState) -> PatientRoutingState:
        return self.graph.invoke(state)
