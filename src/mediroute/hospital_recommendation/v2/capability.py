"""Can this hospital do the procedure the patient mentioned? Three interchangeable methods.

Each method returns a CapabilityResult with a level:

    exact       the hospital lists this procedure (or the same procedure in other words)
    related     it lists a closely related procedure (same family; the patient should confirm)
    speciality  no matching procedure listed; only the speciality is known

The procedure always comes from the patient's own text (Step 1 never infers one). No procedure
mentioned -> every hospital is "speciality" and capability does not change the ranking. No method
ever says which treatment the patient needs: it only compares the patient's words with the
hospital's list (design rule "no treatment advice").

Methods:
    RuleCapability       word overlap + a small synonym list (today's reranker logic)
    EmbeddingCapability  cosine similarity of the procedure and each listed item (MiniLM)
    LLMCapability        an LLM judge with guards: closed levels, it must quote the item it used
                         and code checks the quote is in that hospital field; any failure ->
                         "speciality" (never a better level than the evidence supports)
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any

EXACT, RELATED, SPECIALITY = "exact", "related", "speciality"
LEVEL_SCORE = {EXACT: 1.0, RELATED: 0.6, SPECIALITY: 0.3}
FIELDS = ("procedures", "subspecialties")

STOPWORDS = {"surgery", "surgeries", "treatment", "procedure", "procedures", "therapy", "and", "the", "of", "for",
             "with", "total", "minimally", "invasive", "advanced", "complex", "my", "a", "an", "to", "in", "through"}
SYNONYMS = {"replacement": "arthroplasty", "arthroplasty": "replacement", "bypass": "cabg", "cabg": "bypass",
            "kidney": "renal", "renal": "kidney", "angioplasty": "pci", "pci": "angioplasty"}


@dataclass
class CapabilityResult:
    level: str
    item: str = ""          # the hospital list item that matched
    field: str = ""
    note: str = ""
    cost: float = 0.0
    details: dict[str, Any] = dc_field(default_factory=dict)

    @property
    def score(self) -> float:
        return LEVEL_SCORE[self.level]


def hospital_items(hospital: dict) -> list[tuple[str, str]]:
    """(field, item) for every listed procedure and sub-speciality."""
    out = []
    for name in FIELDS:
        for item in str(hospital.get(name) or "").split(";"):
            item = item.strip()
            if item and item.upper() != "NA":
                out.append((name, item))
    return out


def _words(text: str) -> set[str]:
    words = {w for w in re.findall(r"[a-z0-9]+", text.casefold()) if w not in STOPWORDS}
    return words | {SYNONYMS[w] for w in words if w in SYNONYMS}


# --------------------------------------------------------------------------------- rules
class RuleCapability:
    name = "rules"

    def judge(self, procedure: str, hospital: dict) -> CapabilityResult:
        wanted = _words(procedure)
        if not wanted:
            return CapabilityResult(SPECIALITY, note="no key words")
        best: tuple[float, str, str] = (0.0, "", "")
        for name, item in hospital_items(hospital):
            have = _words(item)
            share = len(wanted & have) / len(wanted)
            if share > best[0]:
                best = (share, name, item)
        share, name, item = best
        if share == 1.0:
            return CapabilityResult(EXACT, item, name, "all key words match")
        if share >= 0.5:
            return CapabilityResult(RELATED, item, name, f"{share:.0%} of key words match")
        return CapabilityResult(SPECIALITY, note="no listed item matches")


# --------------------------------------------------------------------------------- embeddings
class EmbeddingCapability:
    """Thresholds fixed before evaluation (not tuned on the gold set)."""

    name = "embeddings"
    MODEL = "sentence-transformers/all-MiniLM-L6-v2"
    EXACT_MIN, RELATED_MIN = 0.70, 0.50

    def __init__(self, encoder=None) -> None:
        self._encoder = encoder
        self._cache: dict[str, Any] = {}

    def _encode(self, texts: list[str]):
        import numpy as np
        if self._encoder is None:
            from sentence_transformers import SentenceTransformer
            self._encoder = SentenceTransformer(self.MODEL)
        missing = [t for t in texts if t not in self._cache]
        if missing:
            for t, v in zip(missing, self._encoder.encode(missing, normalize_embeddings=True, show_progress_bar=False)):
                self._cache[t] = np.asarray(v, dtype="float32")
        return [self._cache[t] for t in texts]

    def judge(self, procedure: str, hospital: dict) -> CapabilityResult:
        items = hospital_items(hospital)
        if not items:
            return CapabilityResult(SPECIALITY, note="no listed items")
        need, *vectors = self._encode([procedure] + [item for _, item in items])
        scores = [float(need @ v) for v in vectors]
        i = max(range(len(scores)), key=scores.__getitem__)
        name, item = items[i]
        if scores[i] >= self.EXACT_MIN:
            return CapabilityResult(EXACT, item, name, f"similarity {scores[i]:.2f}")
        if scores[i] >= self.RELATED_MIN:
            return CapabilityResult(RELATED, item, name, f"similarity {scores[i]:.2f}")
        return CapabilityResult(SPECIALITY, note=f"best similarity {scores[i]:.2f}")


# --------------------------------------------------------------------------------- LLM judge
LLM_PROMPT = """You help a hospital-discovery service. A patient has ALREADY been told by their own doctor which
procedure they need; you never give medical advice and never suggest a different treatment.
Your only job: does this hospital's list contain the procedure the patient mentioned?

Patient mentioned: "{procedure}"
Hospital: {name}
Listed procedures: {procedures}
Listed sub-specialities: {subspecialties}

Answer with one level:
- "exact": a listed item is this procedure, possibly in other words or as a specific technique of it
  (e.g. "heart bypass" = "CABG"; "valve replacement through a catheter" = "TAVR").
- "related": a listed item is a closely related procedure of the same family that the patient should
  confirm with the hospital (e.g. patient "knee replacement", hospital "Joint Replacement").
- "none": nothing listed covers it.
"item" must be copied exactly from the lists above (empty for "none"); "field" is "procedures" or
"subspecialties". Answer with JSON only."""

LLM_SCHEMA = {"type": "object",
              "properties": {"level": {"type": "string", "enum": ["exact", "related", "none"]},
                             "item": {"type": "string"},
                             "field": {"type": "string", "enum": ["procedures", "subspecialties", ""]},
                             "reason": {"type": "string"}},
              "required": ["level", "item", "field", "reason"]}


class LLMCapability:
    """Guarded LLM judge; answers are cached on disk so reruns cost nothing."""

    name = "llm"
    DEFAULT_MODEL = "openai/gpt-6-luna"
    MIN_SECONDS_BETWEEN_CALLS = 3.3  # OpenRouter new accounts: 20 requests/minute per model

    def __init__(self, client=None, cache_file: Path | None = None, model: str | None = None,
                 budget_usd: float | None = None) -> None:
        self.model = model or os.getenv("MEDIROUTE_CAPABILITY_MODEL", self.DEFAULT_MODEL)
        if client is None:
            from mediroute.specialty_routing.step1.ollama_client import OpenRouterClient
            client = OpenRouterClient(model=self.model)
        self.client = client
        self.cache_file = cache_file
        self.cache: dict[str, dict] = {}
        if cache_file and cache_file.exists():
            for line in cache_file.read_text(encoding="utf-8").splitlines():
                rec = json.loads(line)
                if rec.get("ok"):
                    self.cache[rec["key"]] = rec
        self.budget_usd = budget_usd
        # cumulative: earlier runs' spend (recorded in the cache file) counts against the budget
        self.spent = sum(float(rec.get("cost") or 0) for rec in self.cache.values())
        self._lock = threading.Lock()
        self._next_call = 0.0

    def _key(self, procedure: str, hospital: dict) -> str:
        payload = f"{self.model}|{procedure.casefold()}|{hospital.get('hospital_id')}|{hospital.get('procedures')}|{hospital.get('subspecialties')}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]

    def _call(self, procedure: str, hospital: dict) -> dict:
        key = self._key(procedure, hospital)
        if key in self.cache:
            return self.cache[key]
        if self.budget_usd is not None and self.spent >= self.budget_usd:
            return {"key": key, "ok": False, "error": "budget reached"}
        prompt = LLM_PROMPT.format(procedure=procedure, name=hospital.get("hospital_name", ""),
                                   procedures=hospital.get("procedures") or "(none)",
                                   subspecialties=hospital.get("subspecialties") or "(none)")
        for attempt in range(5):
            with self._lock:
                wait = self._next_call - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                self._next_call = time.monotonic() + self.MIN_SECONDS_BETWEEN_CALLS
            if hasattr(self.client, "_model_down"):
                self.client._model_down.clear()
                self.client._down_reason = ""
            call = self.client.generate_json(prompt, LLM_SCHEMA, purpose="step2_capability")
            if call.ok or "429" not in str(call.error):
                break
            time.sleep(15 * (attempt + 1))
        cost = float((call.details or {}).get("cost") or 0)
        rec = {"key": key, "ok": call.ok, "parsed": call.parsed, "error": call.error, "cost": cost,
               "ms": call.duration_ms, "hospital_id": hospital.get("hospital_id"), "procedure": procedure}
        with self._lock:
            self.spent += cost
            if call.ok:
                self.cache[key] = rec
                if self.cache_file:
                    with self.cache_file.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec

    def judge(self, procedure: str, hospital: dict) -> CapabilityResult:
        rec = self._call(procedure, hospital)
        if not rec.get("ok"):
            return CapabilityResult(SPECIALITY, note=f"LLM failed: {str(rec.get('error'))[:80]}")
        parsed = rec["parsed"]
        level = parsed.get("level")
        if level not in ("exact", "related"):
            return CapabilityResult(SPECIALITY, note=parsed.get("reason", ""), cost=rec.get("cost", 0))
        name, item = parsed.get("field", ""), str(parsed.get("item") or "").strip()
        listed = {i.casefold() for f, i in hospital_items(hospital) if f == name}
        if not item or item.casefold() not in listed:  # guard: the quoted item must really be listed
            return CapabilityResult(SPECIALITY, note=f"guard: item {item!r} not in {name}", cost=rec.get("cost", 0))
        return CapabilityResult(EXACT if level == "exact" else RELATED, item, name, parsed.get("reason", ""),
                                cost=rec.get("cost", 0))


def make_capability(name: str, **kwargs):
    return {"rules": RuleCapability, "embeddings": EmbeddingCapability, "llm": LLMCapability}[name](**kwargs)
