"""Stage 4, three independent voters. Each returns its top-3 specialities.

* V1 keyword: TF-IDF search of each evidence phrase over the lookup list (ICD-10-CM + CGHS).
* V2 meaning: embedding search of each evidence phrase over the same list.
* V3 LLM: picks directly from the canonical speciality list (JSON-schema enum, temperature 0);
  it reads the whole text and does not use the lookup list, which keeps it independent.

V1 and V2 score a speciality by its best hit for each phrase, summed over phrases, so one strong
match for "knee replacement" counts more than many weak partial matches.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mediroute.common.specialties import specialty_names
from mediroute.specialty_routing.routes import UNCLEAR, LLMRouter
from mediroute.specialty_routing.step1.lookup import LookupIndex
from mediroute.specialty_routing.step1.ollama_client import LLMCall, OllamaClient, make_llm_client

CATCH_ALL = "General Medicine"
KEYWORD_MIN_SCORE = 0.25
EMBEDDING_MIN_SCORE = 0.45
HITS_PER_PHRASE = 8


@dataclass
class Vote:
    voter: str
    top3: list[tuple[str, float]] = field(default_factory=list)  # (speciality, score), best first
    ok: bool = True
    ms: int = 0
    hits: list[dict[str, Any]] = field(default_factory=list)  # what the voter matched, for the trace
    llm_call: LLMCall | None = None
    note: str = ""

    @property
    def top1(self) -> str | None:
        return self.top3[0][0] if self.top3 else None


def _aggregate(per_phrase: list[tuple[str, list[tuple[Any, float]]]], min_score: float) -> tuple[list, list]:
    totals: dict[str, float] = {}
    hits: list[dict[str, Any]] = []
    for phrase, results in per_phrase:
        best: dict[str, float] = {}
        for entry, score in results:
            hits.append({"phrase": phrase, "entry_id": entry.entry_id, "text": entry.text[:120],
                         "specialty": entry.specialty, "score": round(score, 3)})
            if score >= min_score and score > best.get(entry.specialty, 0):
                best[entry.specialty] = score
        # A phrase whose best match is the catch-all ("weakness") is a general symptom: its weaker
        # partial hits ("weakness in arm" -> Neurology) must not turn it into a specialist vote.
        if best and max(best, key=best.get) == CATCH_ALL:
            best = {CATCH_ALL: best[CATCH_ALL]}
        for specialty, score in best.items():
            totals[specialty] = totals.get(specialty, 0) + score
    # General Medicine is the catch-all for general symptoms ("weakness", "fever"): it only wins
    # when no specialist matched, so "weakness + slipped disc" goes to Orthopaedics.
    if any(s != CATCH_ALL for s in totals):
        totals.pop(CATCH_ALL, None)
    ranked = sorted(totals.items(), key=lambda kv: -kv[1])[:3]
    return [(s, round(v, 3)) for s, v in ranked], hits


class KeywordVoter:
    name = "V1_keyword"

    def __init__(self, index: LookupIndex) -> None:
        self.index = index

    def vote(self, phrases: list[str]) -> Vote:
        import time
        start = time.perf_counter()
        per_phrase = [(p, self.index.keyword_search(p, k=HITS_PER_PHRASE)) for p in phrases]
        top3, hits = _aggregate(per_phrase, KEYWORD_MIN_SCORE)
        return Vote(self.name, top3, True, int((time.perf_counter() - start) * 1000), hits,
                    note="" if top3 else f"no lookup match scored >= {KEYWORD_MIN_SCORE}")


class EmbeddingVoter:
    name = "V2_embedding"

    def __init__(self, index: LookupIndex) -> None:
        self.index = index

    def vote(self, phrases: list[str]) -> Vote:
        import time
        start = time.perf_counter()
        per_phrase = [(p, self.index.embedding_search(p, k=HITS_PER_PHRASE)) for p in phrases]
        top3, hits = _aggregate(per_phrase, EMBEDDING_MIN_SCORE)
        return Vote(self.name, top3, True, int((time.perf_counter() - start) * 1000), hits,
                    note="" if top3 else f"no lookup match scored >= {EMBEDDING_MIN_SCORE}")


class LLMVoter:
    name = "V3_llm"

    def __init__(self, client: OllamaClient | None = None) -> None:
        self.client = client or make_llm_client()
        self._router = LLMRouter(model=self.client.model)  # reuses the specialty_v1 prompt and enum schema
        self.prompt_version = self._router.prompt_version
        self.valid = set(specialty_names())

    def vote(self, text: str) -> Vote:
        call = self.client.generate_json(self._router.build_prompt(text), self._router.schema, purpose="specialty_vote")
        if not call.ok:
            return Vote(self.name, [], False, call.duration_ms, llm_call=call, note=f"LLM failed: {call.error}")
        primary = str(call.parsed.get("specialty") or "").strip()
        rejected = []
        if primary not in self.valid:
            if primary and primary != UNCLEAR:
                rejected.append(primary)  # schema should prevent this; code checks anyway
            primary = ""
        alternatives = []
        for name in call.parsed.get("alternatives") or []:
            name = str(name).strip()
            if name in self.valid and name != primary and name not in alternatives:
                alternatives.append(name)
            elif name not in self.valid:
                rejected.append(name)
        # "Unclear" means V3 abstains: its alternatives are logged but don't become its vote
        ranked = [primary] + alternatives if primary else []
        # the LLM gives an order, not a calibrated score: 1.0, 0.5, 0.33 by rank
        top3 = [(name, round(1 / (i + 1), 2)) for i, name in enumerate(ranked[:3])]
        note = "LLM answered Unclear (abstains)" if not primary else ""
        if rejected:
            note = (note + "; " if note else "") + f"rejected names not on the list: {rejected}"
        return Vote(self.name, top3, True, call.duration_ms,
                    hits=[{"evidence_terms": call.parsed.get("evidence_terms") or [],
                           "alternatives": alternatives}], llm_call=call, note=note)
