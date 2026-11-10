"""Stage 3, extract evidence: the LLM copies conditions, procedures and body parts from the text;
code then keeps only phrases that really appear in the patient's text.

The check is fuzzy (most words must be present, small typos allowed) because the LLM often
normalises spelling, and patient text and OCR'd reports contain typos. If the LLM is unavailable,
a rule extractor (speciality keywords from specialties.csv found in the text) is used instead.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path

from mediroute.common.specialties import load_specialties
from mediroute.specialty_routing.step1.ollama_client import LLMCall, OllamaClient

PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"
EVIDENCE_PROMPT_VERSION = "evidence_v1"
KINDS = ("conditions", "procedures", "body_parts")
# keyword_matches: speciality keywords (specialties.csv) found word-for-word in the text. They are
# always added, because the small local LLM sometimes misses obvious phrases ("vision is blurry").
ALL_KINDS = KINDS + ("keyword_matches",)

_STOP = {"the", "a", "an", "of", "and", "or", "in", "on", "for", "to", "with", "my", "his", "her", "both",
         "left", "right", "is", "was", "has", "have", "had", "need", "needs", "from", "at", "by", "as", "be"}
# common abbreviations patients and reports use, both directions
_ABBREVIATIONS = {
    "oa": "osteoarthritis", "tkr": "knee replacement", "thr": "hip replacement", "cabg": "bypass",
    "ckd": "kidney disease", "esrd": "renal disease", "mi": "heart attack", "af": "atrial fibrillation",
    "ivf": "in vitro fertilisation", "acl": "anterior cruciate ligament", "uti": "urinary infection",
}

EVIDENCE_SCHEMA = {
    "type": "object",
    "properties": {kind: {"type": "array", "items": {"type": "string"}, "maxItems": 6} for kind in KINDS},
    "required": list(KINDS),
}


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if t not in _STOP and len(t) > 1]


def verify_phrase(phrase: str, source_tokens: set[str]) -> tuple[bool, float]:
    """A phrase is supported if at least 60% of its words (abbreviations expanded) are in the source,
    exactly or as a close spelling (similarity >= 0.85)."""
    words = _tokens(phrase)
    if not words:
        return False, 0.0
    found = 0
    for word in words:
        if word in source_tokens:
            found += 1
            continue
        expansion = _ABBREVIATIONS.get(word)
        reverse = [abbr for abbr, full in _ABBREVIATIONS.items() if word in full.split()]
        if (expansion and set(_tokens(expansion)) & source_tokens) or any(a in source_tokens for a in reverse):
            found += 1
            continue
        if len(word) >= 4 and difflib.get_close_matches(word, source_tokens, n=1, cutoff=0.85):
            found += 1
    share = found / len(words)
    return share >= 0.6, round(share, 2)


@dataclass
class Evidence:
    method: str  # "llm+keywords" or "keywords_only" (LLM unavailable)
    kept: dict[str, list[str]] = field(default_factory=lambda: {k: [] for k in ALL_KINDS})
    dropped: list[dict] = field(default_factory=list)
    llm_call: LLMCall | None = None

    @property
    def phrases(self) -> list[str]:
        """Conditions and procedures first (they decide the speciality), then keywords, then body parts."""
        ordered = (self.kept["conditions"] + self.kept["procedures"] + self.kept["keyword_matches"]
                   + self.kept["body_parts"])
        return _dedupe_contained(ordered)

    @property
    def routing_phrases(self) -> list[str]:
        """Phrases the search voters use; body parts only if nothing else was found."""
        main = _dedupe_contained(self.kept["conditions"] + self.kept["procedures"] + self.kept["keyword_matches"])
        return main or _dedupe_contained(self.kept["body_parts"])


def _dedupe_contained(phrases: list[str]) -> list[str]:
    """Drop duplicates (ignoring case) and a phrase already contained in a longer kept phrase
    ("knee" in "knee pain"). The first spelling seen is kept, so LLM phrases win over keywords."""
    by_lower: dict[str, str] = {}
    for phrase in phrases:
        phrase = phrase.strip()
        if phrase and phrase.lower() not in by_lower:
            by_lower[phrase.lower()] = phrase
    unique = list(by_lower.values())
    lowered = list(by_lower.keys())
    return [p for p, low in zip(unique, lowered)
            if not any(low != other and f" {low} " in f" {other} " for other in lowered)]


class EvidenceExtractor:
    def __init__(self, client: OllamaClient | None = None) -> None:
        self.client = client or OllamaClient()
        self.template = (PROMPT_DIR / f"{EVIDENCE_PROMPT_VERSION}.txt").read_text(encoding="utf-8")
        self._keywords = [(kw, spec.name) for spec in load_specialties() for kw in spec.keywords]

    def build_prompt(self, text: str) -> str:
        return self.template.format(text=text.strip())

    def extract(self, text: str) -> Evidence:
        keywords = self.keyword_matches(text)
        call = self.client.generate_json(self.build_prompt(text), EVIDENCE_SCHEMA, purpose="evidence_extraction")
        if not call.ok:
            evidence = Evidence(method="keywords_only", llm_call=call)
            evidence.kept["keyword_matches"] = keywords
            return evidence
        source = set(_tokens(text))
        evidence = Evidence(method="llm+keywords", llm_call=call)
        evidence.kept["keyword_matches"] = keywords
        for kind in KINDS:
            for phrase in call.parsed.get(kind) or []:
                phrase = str(phrase).strip()
                if not phrase:
                    continue
                if re.search(r"\[(PHONE|EMAIL|ID)\]", phrase):  # redacted contact details are not evidence
                    evidence.dropped.append({"kind": kind, "phrase": phrase, "matched_share": None,
                                             "why": "contains redacted identifier"})
                    continue
                supported, share = verify_phrase(phrase, source)
                if supported:
                    if phrase not in evidence.kept[kind]:
                        evidence.kept[kind].append(phrase)
                else:
                    evidence.dropped.append({"kind": kind, "phrase": phrase, "matched_share": share})
        return evidence

    def keyword_matches(self, text: str) -> list[str]:
        """Speciality keywords that appear word-for-word in the text (deterministic)."""
        lowered = " " + re.sub(r"[^a-z0-9']+", " ", text.lower()) + " "
        found = [kw for kw, _ in self._keywords if f" {re.sub(r'[^a-z0-9]+', ' ', kw).strip()} " in lowered]
        found = [k for k in found if not any(k != o and k in o for o in found)]  # keep the longer phrase
        return list(dict.fromkeys(found))[:8]
