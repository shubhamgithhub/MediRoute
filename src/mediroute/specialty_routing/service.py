"""Step 1 service used by the API: one instance per process, chosen by MEDIROUTE_ROUTING_MODE.

Modes:
    vote    three voters + majority + clarification form (default; step1/pipeline.py)
    rules   deterministic keyword route only        (baseline, kept for scripts/eval_step1.py)
    llm     local LLM only                          (baseline)
    hybrid  LLM decides, rules give a second opinion (earlier design, kept for comparison)
"""

from __future__ import annotations

import hashlib
import os
from functools import lru_cache

from mediroute.common.specialties import care_category, get_specialty
from mediroute.specialty_routing.routes import UNCLEAR, LLMRouter, RouteResult, RuleRouter, combine
from mediroute.utils.logging_config import get_logger

logger = get_logger()

DISCLAIMER = "Hospital discovery support only, not a diagnosis or medical advice."
CLARIFY_QUESTION = (
    "Could you describe the main problem in a little more detail: which part of the body, "
    "how long it has lasted, and any diagnosis or test result you already have?"
)


class SpecialtyService:
    def __init__(self, mode: str | None = None) -> None:
        self.mode = (mode or os.getenv("MEDIROUTE_ROUTING_MODE", "vote")).lower()
        if self.mode not in {"vote", "rules", "llm", "hybrid"}:
            raise ValueError(f"Unknown routing mode: {self.mode}")
        self.rules = RuleRouter()
        self.llm = LLMRouter() if self.mode in {"llm", "hybrid"} else None
        self.pipeline = None
        if self.mode == "vote":
            from mediroute.specialty_routing.step1.pipeline import Step1Pipeline
            self.pipeline = Step1Pipeline()

    def analyze_request(self, request) -> dict:
        """Step 1 for a PatientRequest. The vote pipeline uses reports and clarification answers;
        the baseline modes only read the text."""
        text = request.requirement or request.additionalPreference or ""
        if self.pipeline is None:
            return self.analyze(text)
        from mediroute.specialty_routing.step1.pipeline import Step1Input
        return self.pipeline.analyze(Step1Input(
            text=text,
            report_text=request.reportText or "",
            clarification=request.clarification.model_dump() if request.clarification else {},
            clarification_round=request.clarificationRound,
            selected_specialty=request.selectedSpecialty,
            parent_request_id=request.parentRequestId,
            debug=request.debug,
        ))

    def warm_up(self) -> None:
        if self.pipeline is not None:
            self.pipeline.warm_up(logger)
            return
        if self.llm:
            try:
                self.llm.warm_up()
                logger.info("LLM warm-up done: model=%s", self.llm.model)
            except Exception as exc:  # the API still works on rules
                logger.warning("LLM warm-up failed (%s); hybrid mode will fall back to rules", exc)

    def _route(self, text: str) -> tuple[RouteResult, str]:
        if self.mode == "rules":
            result = self.rules.route(text)
            if result.primary == UNCLEAR:
                return result, "low"
            top = result.scores.get(result.primary, 0)
            second = sorted(result.scores.values(), reverse=True)[1] if len(result.scores) > 1 else 0
            return result, "high" if top >= 2 and top > second else "medium"
        if self.mode == "llm":
            result = self.llm.route(text)
            return result, "low" if result.primary == UNCLEAR else "medium"
        rules_result = self.rules.route(text)
        llm_result = self.llm.route(text)
        result, confidence = combine(llm_result, rules_result)
        result.latency_ms = llm_result.latency_ms + rules_result.latency_ms
        return result, confidence

    def analyze(self, text: str) -> dict:
        if self.pipeline is not None:  # plain-text callers (tests, scripts) also get the vote pipeline
            from mediroute.specialty_routing.step1.pipeline import Step1Input
            return self.pipeline.analyze(Step1Input(text=text or ""))
        text = (text or "").strip()
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
        if not text:
            result, confidence = RouteResult(UNCLEAR, reason="No patient input was provided."), "low"
        else:
            result, confidence = self._route(text)

        clarify = confidence == "low" or result.primary == UNCLEAR
        specialty = get_specialty(result.primary)
        primary = result.primary if result.primary != UNCLEAR else "General Medicine"
        # privacy: log a hash and length of the patient text, never the text itself
        logger.info("step1 query=%s len=%d mode=%s -> %s (%s, %d ms, route=%s)", digest, len(text),
                    self.mode, result.primary, confidence, result.latency_ms, result.route)
        return {
            # fields the current frontend reads
            "relevantSpecialty": primary,
            "careCategory": care_category(primary),
            "reasoning": [result.reason] if result.reason else [],
            "matched_terms": result.evidence_terms,
            "requires_human_review": clarify,
            # new contract (design §5)
            "primary_specialty": None if result.primary == UNCLEAR else result.primary,
            "alternatives": [s for s in result.ranked if s != result.primary][:2],
            "confidence": confidence,
            "evidence_terms": result.evidence_terms,
            "reason": result.reason,
            "in_hospital_data": bool(specialty and specialty.in_hospital_data),
            "clarification_required": clarify,
            "clarification_question": CLARIFY_QUESTION if clarify else None,
            "mode_used": result.route or self.mode,
            "model": self.llm.model if self.llm else None,
            "prompt_version": self.llm.prompt_version if self.llm else None,
            "latency_ms": result.latency_ms,
            "disclaimer": DISCLAIMER,
        }


@lru_cache(maxsize=1)
def get_service() -> SpecialtyService:
    """Build the service once per process (not per request)."""
    return SpecialtyService()
