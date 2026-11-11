"""Two Step 1 routes from patient text to specialty.

* RuleRouter: deterministic matching of the lay terms in data/processed/specialty_mapping.csv
  (a baseline; the app uses the Step 1 vote pipeline in step1/).
* LLMRouter: a local open-source LLM (Ollama) that must pick a name from the canonical list,
  enforced by a JSON-schema enum.

Both return a RouteResult so they can be evaluated side by side (scripts/eval_step1.py).
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from mediroute.common.specialties import Specialty, lay_terms, load_specialties, specialty_names

UNCLEAR = "Unclear"
PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
# specialty_v2: the same prompt, but each speciality line adds its routing boundaries
# (route_here_when / not_here from specialties.csv). specialty_v1 lists name: description only.
DEFAULT_PROMPT_VERSION = "specialty_v2"
DEFAULT_MODEL = os.getenv("MEDIROUTE_LLM_MODEL", "llama3.2")
DEFAULT_OLLAMA_URL = os.getenv("OLLAMA_API_BASE_URL", "http://127.0.0.1:11434")  # see step1/ollama_client.py


@dataclass
class RouteResult:
    primary: str  # a canonical specialty name, or UNCLEAR
    ranked: list[str] = field(default_factory=list)  # primary first, up to 3 names
    evidence_terms: list[str] = field(default_factory=list)
    reason: str = ""
    route: str = ""
    ok: bool = True  # False when the route failed (e.g. LLM unreachable)
    latency_ms: int = 0
    scores: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Route 1: deterministic rules
# ---------------------------------------------------------------------------


def normalize_text(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9']+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class RuleRouter:
    """Score each specialty by the keywords found in the text.

    A keyword counts once, as a whole-word phrase. Multi-word phrases weigh more because they
    are more specific ("knee replacement" beats "knee"). Ties keep the CSV order. No match
    returns UNCLEAR.
    """

    name = "rules"

    def __init__(self, specialties: tuple[Specialty, ...] | None = None) -> None:
        self.specialties = specialties or load_specialties()
        by_specialty: dict[str, list[str]] = {spec.name: [] for spec in self.specialties}
        for rule in lay_terms():  # every lay term (strong and weak) in specialty_mapping.csv
            for name in rule.specialties:
                if name in by_specialty:
                    by_specialty[name].append(rule.value)
        self._patterns = [
            (
                name,
                [
                    (kw, re.compile(r"\b" + re.escape(normalize_text(kw)) + r"\b"))
                    for kw in keywords
                    if normalize_text(kw)
                ],
            )
            for name, keywords in by_specialty.items()
        ]

    def route(self, text: str) -> RouteResult:
        start = time.perf_counter()
        normalized = normalize_text(text)
        scores: dict[str, float] = {}
        terms: dict[str, list[str]] = {}
        for name, patterns in self._patterns:
            matched = [kw for kw, pattern in patterns if pattern.search(normalized)]
            # drop a keyword that is part of a longer matched keyword ("stone" in "kidney stone")
            matched = [m for m in matched if not any(m != o and m in o for o in matched)]
            if matched:
                scores[name] = sum(1.0 + 0.5 * (len(m.split()) - 1) for m in matched)
                terms[name] = matched

        ranked = sorted(scores, key=lambda n: -scores[n])  # stable: ties keep CSV order
        latency = int((time.perf_counter() - start) * 1000)
        if not ranked:
            return RouteResult(UNCLEAR, [], [], "No known symptom or condition terms found.",
                               self.name, True, latency, {})
        primary = ranked[0]
        return RouteResult(
            primary=primary,
            ranked=ranked[:3],
            evidence_terms=terms[primary],
            reason=f"Matched terms for {primary}: {', '.join(terms[primary])}.",
            route=self.name,
            ok=True,
            latency_ms=latency,
            scores={n: scores[n] for n in ranked[:3]},
        )


# ---------------------------------------------------------------------------
# Route 2: local LLM constrained to the canonical list
# ---------------------------------------------------------------------------


def load_prompt(version: str = DEFAULT_PROMPT_VERSION) -> str:
    return (PROMPT_DIR / f"{version}.txt").read_text(encoding="utf-8")


class LLMRouter:
    name = "llm"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_OLLAMA_URL,
        prompt_version: str = DEFAULT_PROMPT_VERSION,
        timeout_s: float = 90.0,
        specialties: tuple[Specialty, ...] | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.prompt_version = prompt_version
        self.timeout_s = timeout_s
        self.specialties = specialties or load_specialties()
        self.names = [s.name for s in self.specialties]
        self.template = load_prompt(prompt_version)
        options = self.names + [UNCLEAR]
        self.schema = {
            "type": "object",
            "properties": {
                "specialty": {"type": "string", "enum": options},
                "alternatives": {
                    "type": "array",
                    "items": {"type": "string", "enum": self.names},
                    "maxItems": 2,
                },
                "evidence_terms": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
            },
            # No free-text "reason": on CPU it tripled latency (about 20 s vs 6-7 s). The
            # explanation is built from evidence_terms, which are words from the patient's text.
            "required": ["specialty", "alternatives", "evidence_terms"],
        }

    def build_prompt(self, text: str) -> str:
        catalogue = "\n".join(f"- {s.name}: {s.description}" for s in self.specialties)
        return self.template.format(specialties=catalogue, query=text.strip())

    def _post(self, payload: dict) -> dict:
        request = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
            return json.loads(response.read().decode("utf-8"))

    def warm_up(self) -> None:
        """Load the model into memory so the first real request is not slow."""
        self._post({"model": self.model, "prompt": "ok", "stream": False,
                    "keep_alive": "30m", "options": {"num_predict": 1}})

    def route(self, text: str) -> RouteResult:
        start = time.perf_counter()
        try:
            body = self._post({
                "model": self.model,
                "prompt": self.build_prompt(text),
                "stream": False,
                "format": self.schema,
                "keep_alive": "30m",
                "options": {"temperature": 0, "seed": 7},
            })
            parsed = json.loads(body.get("response") or "{}")
        except Exception as exc:  # network, timeout, bad JSON
            return RouteResult(UNCLEAR, [], [], f"LLM call failed: {type(exc).__name__}",
                               self.name, False, int((time.perf_counter() - start) * 1000))

        latency = int((time.perf_counter() - start) * 1000)
        valid = set(self.names)
        primary = str(parsed.get("specialty") or "").strip()
        if primary not in valid and primary != UNCLEAR:  # schema should prevent this; check anyway
            primary = UNCLEAR
        alternatives = [a for a in parsed.get("alternatives") or [] if a in valid and a != primary]
        ranked = ([primary] if primary != UNCLEAR else []) + list(dict.fromkeys(alternatives))
        evidence = [str(t) for t in parsed.get("evidence_terms") or []][:5]
        return RouteResult(
            primary=primary,
            ranked=ranked[:3],
            evidence_terms=evidence,
            reason=(f"Routed to {primary} because of: {', '.join(evidence)}." if primary != UNCLEAR and evidence
                    else "The message was too vague to choose a specialty." if primary == UNCLEAR
                    else f"Routed to {primary}."),
            route=self.name,
            ok=True,
            latency_ms=latency,
        )


# ---------------------------------------------------------------------------
# Hybrid: LLM decides, rules give a second opinion and the fallback
# ---------------------------------------------------------------------------


def combine(llm: RouteResult, rules: RouteResult) -> tuple[RouteResult, str]:
    """Return the hybrid result and a confidence label (high / medium / low).

    high:   LLM and rules agree on the primary specialty
    medium: LLM's pick appears in the rules' top 3, or the rules' pick is in the LLM's top 3
    low:    they disagree, the LLM said Unclear, or the LLM failed (rules used as fallback)
    """
    if not llm.ok or llm.primary == UNCLEAR:
        fallback = RouteResult(**{**rules.__dict__, "route": "hybrid:rules_fallback"})
        return fallback, "low"
    result = RouteResult(**{**llm.__dict__, "route": "hybrid"})
    if rules.primary == llm.primary:
        return result, "high"
    if llm.primary in rules.ranked or rules.primary in llm.ranked:
        return result, "medium"
    return result, "low"


__all__ = ["RouteResult", "RuleRouter", "LLMRouter", "combine", "UNCLEAR", "specialty_names"]
