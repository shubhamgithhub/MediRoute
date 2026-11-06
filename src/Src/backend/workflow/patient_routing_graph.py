
from langgraph.graph import StateGraph, START, END

from src.Src.backend.workflow.routing_state import (
    PatientRoutingState,
)

from src.Src.backend.workflow.routing_nodes import (
    RoutingNodes,
)

from src.Src.backend.workflow.routing_decisions import (
    decide_after_report_parsing,
    decide_after_medical_validation,
    decide_after_recommendation,
)


class PatientRoutingGraph:

    def __init__(self):
        self.nodes = RoutingNodes()
        self.graph = self._build_graph()

    def _build_graph(self):

        builder = StateGraph(PatientRoutingState)

        # =========================================
        # STEP 8 — PDF PARSING
        # =========================================

        builder.add_node(
            "parse_reports",
            self.nodes.parse_reports,
        )

        # =========================================
        # STEP 9 — MEDICAL EXTRACTION & VALIDATION
        # =========================================

        builder.add_node(
            "extract_medical_context",
            self.nodes.extract_medical_context,
        )

        builder.add_node(
            "validate_medical_context",
            self.nodes.validate_medical_context,
        )

        # =========================================
        # STEP 11 — HOSPITAL RECOMMENDATIONS
        # =========================================

        builder.add_node(
            "recommend_hospitals",
            self.nodes.recommend_hospitals,
        )

        # =========================================
        # CLARIFICATION / FINALIZATION / ERRORS
        # =========================================

        builder.add_node(
            "medical_clarification",
            self.nodes.create_clarification,
        )

        builder.add_node(
            "location_clarification",
            self.nodes.create_location_clarification,
        )

        builder.add_node(
            "finalize",
            self.nodes.finalize,
        )

        builder.add_node(
            "error",
            self.nodes.handle_error,
        )

        # =========================================
        # START — BEGIN WITH PDF PARSING
        # =========================================

        builder.add_edge(
            START,
            "parse_reports",
        )

        # =========================================
        # DECISION AFTER PDF PARSING
        # =========================================

        builder.add_conditional_edges(
            "parse_reports",
            decide_after_report_parsing,
            {
                "extract": "extract_medical_context",
                "clarify": "medical_clarification",
                "error": "error",
            },
        )

        # =========================================
        # EXTRACTION → MEDICAL VALIDATION
        # =========================================

        builder.add_edge(
            "extract_medical_context",
            "validate_medical_context",
        )

        # =========================================
        # DECISION AFTER MEDICAL VALIDATION
        # =========================================

        builder.add_conditional_edges(
            "validate_medical_context",
            decide_after_medical_validation,
            {
                "recommend": "recommend_hospitals",
                "clarify": "medical_clarification",
                "error": "error",
            },
        )

        # =========================================
        # DECISION AFTER RECOMMENDATION
        # =========================================

        builder.add_conditional_edges(
            "recommend_hospitals",
            decide_after_recommendation,
            {
                "finish": "finalize",
                "clarify_location": "location_clarification",
                "clarify_medical": "medical_clarification",
                "error": "error",
            },
        )

        # =========================================
        # END PATHS
        # =========================================

        builder.add_edge("medical_clarification", END)
        builder.add_edge("location_clarification", END)
        builder.add_edge("finalize", END)
        builder.add_edge("error", END)

        return builder.compile()

    def invoke(
        self,
        state: PatientRoutingState,
    ) -> PatientRoutingState:

        return self.graph.invoke(state)
