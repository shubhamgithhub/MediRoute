"""Stage 4, the voters. Each returns its top-3 specialities.

The app uses two independent voters (decided in pipeline.py; a judge settles disagreements):

* V1 lookup (HybridLookupVoter): each evidence phrase is searched in the lookup list (ICD-10-CM
  via CCSR, CGHS, lay terms) by keyword (TF-IDF) and by meaning (embeddings); the two result lists
  are fused by rank (Reciprocal Rank Fusion), so one voter uses both kinds of search. The old
  design had them as two voters on the same data, whose shared mistakes could outvote the LLM.
* V2 LLM (LLMVoter): picks directly from the speciality master list (names, descriptions and
  routing boundaries; JSON-schema enum, temperature 0). It reads the whole text and does not use
  the lookup list, which keeps it independent.

KeywordVoter and EmbeddingVoter (the two searches alone) are kept for the benchmarks.

Lookup voters score a speciality by its best hit for each phrase, summed over phrases. A hit on
a symptom or a weak lay term (evidence_type in the lookup, from specialty_mapping.csv) counts
half: "back pain" must not outweigh "kidney stone". The lookup voter (V1) also searches each
phrase without its generic words ("problem in my stomach" -> "stomach") and lets each phrase vote
for the speciality of its best match only (other specialities from that phrase count 10%), so weak
hits on several phrases cannot outweigh one clear match (portal benchmark, 11 Nov 2026).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mediroute.common.specialties import WEAK_EVIDENCE, specialty_names
from mediroute.specialty_routing.routes import UNCLEAR, LLMRouter
from mediroute.specialty_routing.step1.evidence import search_text
from mediroute.specialty_routing.step1.lookup import LookupIndex
from mediroute.specialty_routing.step1.ollama_client import LLMCall, OllamaClient, make_llm_client

CATCH_ALL = "General Medicine"
KEYWORD_MIN_SCORE = 0.25
EMBEDDING_MIN_SCORE = 0.45
HITS_PER_PHRASE = 8
RRF_K = 60          # Reciprocal Rank Fusion constant (standard value)
FUSION_DEPTH = 20   # results taken from each search before fusing
RUNNER_UP_WEIGHT = 0.1  # lookup voter: a phrase's other specialities count 10% of its best match
WEAK_EVIDENCE_WEIGHT = 0.5


@dataclass
class Vote:
    voter: str
    top3: list[tuple[str, float]] = field(default_factory=list)  # (speciality, score), best first
    ok: bool = True
    ms: int = 0
    hits: list[dict[str, Any]] = field(default_factory=list)  # what the voter matched, for the trace
    llm_call: LLMCall | None = None
    note: str = ""
    details: dict[str, Any] = field(default_factory=dict)  # how the score was built (admin page)

    @property
    def top1(self) -> str | None:
        return self.top3[0][0] if self.top3 else None


def _aggregate(per_phrase: list[tuple[str, list[tuple[Any, float]]]], min_score: float,
               best_only: bool = False, breakdown: list | None = None) -> tuple[list, list]:
    """best_only: each phrase votes for the speciality of its best match; its other specialities
    count RUNNER_UP_WEIGHT, so weak hits on several phrases cannot outweigh one clear match.
    breakdown: if given, one row per phrase is appended with what it added to each speciality."""
    totals: dict[str, float] = {}
    hits: list[dict[str, Any]] = []
    for phrase, results in per_phrase:
        best: dict[str, float] = {}
        for entry, score in results:
            # General Medicine is the catch-all with its own rules below, so it is not weakened twice
            weak = getattr(entry, "evidence_type", "") in WEAK_EVIDENCE and entry.specialty != CATCH_ALL
            weighted = score * (WEAK_EVIDENCE_WEIGHT if weak else 1.0)
            hits.append({"phrase": phrase, "entry_id": entry.entry_id, "text": entry.text[:120],
                         "specialty": entry.specialty, "score": round(score, 3),
                         "evidence_type": getattr(entry, "evidence_type", ""), "weak": weak,
                         "weighted": round(weighted, 4)})
            if score >= min_score and weighted > best.get(entry.specialty, 0):
                best[entry.specialty] = weighted
        general_only = False
        # A phrase whose best match is the catch-all ("weakness") is a general symptom: its weaker
        # partial hits ("weakness in arm" -> Neurology) must not turn it into a specialist vote.
        if best and max(best, key=best.get) == CATCH_ALL:
            best = {CATCH_ALL: best[CATCH_ALL]}
            general_only = True
        if best_only and best:
            top = max(best.values())
            best = {s: (v if v >= top - 1e-12 else v * RUNNER_UP_WEIGHT) for s, v in best.items()}
        for specialty, score in best.items():
            totals[specialty] = totals.get(specialty, 0) + score
        if breakdown is not None:
            ordered = sorted(best.items(), key=lambda kv: -kv[1])
            breakdown.append({"phrase": phrase, "best": ordered[0][0] if ordered else None,
                              "general_only": general_only,
                              "added": [[s, round(v, 4)] for s, v in ordered]})
    # General Medicine is the catch-all for general symptoms ("weakness", "fever"): it only wins
    # when no specialist matched, so "weakness + slipped disc" goes to Orthopaedics.
    dropped_general = any(s != CATCH_ALL for s in totals) and CATCH_ALL in totals
    if any(s != CATCH_ALL for s in totals):
        totals.pop(CATCH_ALL, None)
    if breakdown is not None:
        breakdown.append({"totals": [[s, round(v, 4)] for s, v in sorted(totals.items(), key=lambda kv: -kv[1])],
                          "dropped_general_medicine": dropped_general})
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


class HybridLookupVoter:
    """V1: keyword and meaning search over the lookup list, fused per phrase by rank (RRF)."""

    name = "V1_lookup"

    PARAMS = {
        "keyword_search": "TF-IDF, 0.5 x word (1-2 words) + 0.5 x character (3-5 letters), cosine",
        "keyword_min_score": KEYWORD_MIN_SCORE,
        "meaning_search": "all-MiniLM-L6-v2 sentence embeddings, cosine",
        "meaning_min_score": EMBEDDING_MIN_SCORE,
        "results_per_search": FUSION_DEPTH,
        "fusion": f"Reciprocal Rank Fusion: sum of 1 / ({RRF_K} + rank) over both searches",
        "rrf_k": RRF_K,
        "entries_kept_per_phrase": HITS_PER_PHRASE,
        "runner_up_weight": RUNNER_UP_WEIGHT,
        "weak_evidence_weight": WEAK_EVIDENCE_WEIGHT,
    }

    def __init__(self, index: LookupIndex) -> None:
        self.index = index

    def _fused(self, phrase: str, seen: dict | None = None) -> list[tuple[Any, float]]:
        """seen: filled with entry_id -> {keyword rank/score, meaning rank/score} for the trace."""
        query = search_text(phrase)  # generic words removed: "problem in my stomach" -> "stomach"
        keyword = [(e, s) for e, s in self.index.keyword_search(query, k=FUSION_DEPTH) if s >= KEYWORD_MIN_SCORE]
        try:
            meaning = [(e, s) for e, s in self.index.embedding_search(query, k=FUSION_DEPTH) if s >= EMBEDDING_MIN_SCORE]
        except Exception:  # embedding model unavailable: keyword search alone
            meaning = []
        fused: dict[str, float] = {}
        entries: dict[str, Any] = {}
        for kind, results in (("kw", keyword), ("emb", meaning)):
            for rank, (entry, score) in enumerate(results, 1):
                fused[entry.entry_id] = fused.get(entry.entry_id, 0.0) + 1.0 / (RRF_K + rank)
                entries[entry.entry_id] = entry
                if seen is not None:
                    seen.setdefault(entry.entry_id, {})[kind] = [rank, round(score, 3)]
        if seen is not None:
            seen["_query"] = query
            seen["_counts"] = [len(keyword), len(meaning)]
        ranked = sorted(fused.items(), key=lambda kv: -kv[1])[:HITS_PER_PHRASE]
        return [(entries[i], score) for i, score in ranked]

    def vote(self, phrases: list[str]) -> Vote:
        import time
        start = time.perf_counter()
        seen_by_phrase: dict[str, dict] = {}
        per_phrase = [(p, self._fused(p, seen_by_phrase.setdefault(p, {}))) for p in phrases]
        breakdown: list[dict] = []
        top3, hits = _aggregate(per_phrase, 0.0, best_only=True, breakdown=breakdown)
        for hit in hits:  # which search found each entry, at what rank and score
            found = seen_by_phrase.get(hit["phrase"], {}).get(hit["entry_id"], {})
            hit["kw"], hit["emb"] = found.get("kw"), found.get("emb")
        phrases_detail = []
        for row in breakdown[:-1]:
            seen = seen_by_phrase.get(row["phrase"], {})
            phrases_detail.append({**row, "query": seen.get("_query"),
                                   "keyword_results": (seen.get("_counts") or [0, 0])[0],
                                   "meaning_results": (seen.get("_counts") or [0, 0])[1]})
        details = {"params": self.PARAMS, "phrases": phrases_detail, **(breakdown[-1] if breakdown else {})}
        return Vote(self.name, top3, True, int((time.perf_counter() - start) * 1000), hits,
                    note="" if top3 else "no lookup match", details=details)


class LLMVoter:
    name = "V2_llm"

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
