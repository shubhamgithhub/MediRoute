"""The LLM judge: settles a disagreement between the lookup voter and the LLM voter.

It runs only when the two voters name different specialities. A stronger hosted model (default
GPT-6 Luna via OpenRouter, reasoning off) chooses between the two, under guards that stop it from
inventing answers or evidence:

    closed choice   the JSON schema allows only the two disputed specialities or "unclear"
    cited evidence  it must cite evidence lines (E1, E2 ...) that code built from the lookup list;
                    code checks each exists and that one maps to the chosen speciality
    real quote      its quote must be found in the patient text (verify_phrase)
    order swap      it is asked twice with the candidates in opposite order; both must match
    fail-safe       any failed check, "unclear", error, timeout or missing key -> no answer, and
                    the pipeline asks the patient a question (as before the judge existed)

Benchmarked on 346 gold queries (docs/evaluation/step1_benchmark_report.html): 0 invented answers
passed the guards; about $0.0001 per disagreement.

Configuration: MEDIROUTE_JUDGE_PROVIDER = openrouter (default) | ollama | none,
MEDIROUTE_JUDGE_MODEL (default openai/gpt-6-luna; pinned, no fallback model).
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from mediroute.common.specialties import get_specialty
from mediroute.specialty_routing.step1.evidence import _tokens, search_text, verify_phrase
from mediroute.specialty_routing.step1.ollama_client import (
    DisabledLLMClient,
    LLMCall,
    OllamaClient,
    OpenRouterClient,
)

JUDGE_PROMPT_VERSION = "judge_v1"
DEFAULT_JUDGE_MODEL = "openai/gpt-6-luna"
UNCLEAR = "unclear"
EVIDENCE_K = 200          # how deep to look for the best entry of each candidate speciality
MIN_SEMANTIC, MIN_KEYWORD = 0.35, 0.15  # an evidence line must be at least loosely related

PROMPT = """You help a hospital-discovery service decide which medical speciality a patient should search for.
Two methods disagree. Choose the ONE candidate speciality that best fits the patient's MAIN problem,
using only the patient's text and the evidence lines below. A diagnosis or a planned procedure
outweighs a symptom. If the text does not let you decide, answer "unclear".

Patient text:
\"\"\"{text}\"\"\"

Candidate specialities:
{candidates}

Evidence lines (phrase from the patient's text -> matching medical term in our list -> speciality):
{evidence}

Rules:
- "choice" must be one of the candidates above, or "unclear".
- "evidence" lists the IDs of the evidence lines that support your choice (at least one).
- "patient_quote" copies the exact words from the patient text that decided it.
- "reason" is one short sentence.
Answer with JSON only."""


def make_judge_client():
    """The judge's own LLM client, pinned to one model (no fallback list)."""
    provider = os.getenv("MEDIROUTE_JUDGE_PROVIDER", "openrouter").strip().lower()
    model = os.getenv("MEDIROUTE_JUDGE_MODEL", DEFAULT_JUDGE_MODEL).strip()
    if provider == "openrouter":
        return OpenRouterClient(model=model)
    if provider == "ollama":
        return OllamaClient(model=os.getenv("MEDIROUTE_JUDGE_MODEL", "llama3.2"))
    if provider in {"none", "off", "disabled"}:
        return DisabledLLMClient()
    raise ValueError(f"Unknown MEDIROUTE_JUDGE_PROVIDER '{provider}': use 'openrouter', 'ollama' or 'none'")


def judge_schema(candidates: list[str], evidence_ids: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "choice": {"type": "string", "enum": candidates + [UNCLEAR]},
            "evidence": {"type": "array", "items": {"type": "string", "enum": evidence_ids or ["none"]}},
            "patient_quote": {"type": "string"},
            "reason": {"type": "string"},
        },
        "required": ["choice", "evidence", "patient_quote", "reason"],
    }


@dataclass
class JudgeResult:
    final: str | None                 # the accepted speciality, or None (-> ask the patient)
    status: str                       # accepted | unclear | order-swap flip | check failed | call failed | unavailable
    candidates: list[str]
    evidence_lines: list[dict] = field(default_factory=list)
    choices: list[str | None] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    reason: str = ""
    quote: str = ""
    calls: list[LLMCall] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)

    def trace(self) -> dict[str, Any]:
        return {"status": self.status, "final": self.final, "candidates": self.candidates, "choices": self.choices,
                "failures": self.failures, "reason": self.reason, "patient_quote": self.quote,
                "evidence_lines": self.evidence_lines,
                "cost": sum((c.details or {}).get("cost") or 0 for c in self.calls),
                "ms": max([c.duration_ms for c in self.calls] or [0])}


class LLMJudge:
    def __init__(self, client=None, index=None) -> None:
        self.client = client if client is not None else make_judge_client()
        self.index = index
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="step1-judge")

    def status(self) -> dict[str, Any]:
        status = getattr(self.client, "status", None)
        if status is None:
            return {"provider": "custom", "model": getattr(self.client, "model", ""), "available": True, "reason": ""}
        return status()

    # ----------------------------------------------------------------- evidence lines (built by code)
    def evidence_lines(self, phrases: list[str], candidates: list[str]) -> list[dict]:
        """For each evidence phrase and candidate: the best lookup entry of that speciality, if it is
        at least loosely related. Every line is real data, so the judge cannot cite invented evidence."""
        lines: list[dict] = []
        if self.index is None:
            return lines
        for phrase in phrases:
            query = search_text(phrase)
            keyword = {e.entry_id: s for e, s in self.index.keyword_search(query, k=EVIDENCE_K)}
            try:
                semantic = self.index.embedding_search(query, k=EVIDENCE_K)
            except Exception:  # embedding model unavailable: keyword evidence only
                semantic = [(e, 0.0) for e in self.index.entries if e.entry_id in keyword]
            best: dict[str, tuple[float, Any]] = {}
            for entry, sem in semantic:
                if entry.specialty not in candidates:
                    continue
                kw = keyword.get(entry.entry_id, 0.0)
                if sem < MIN_SEMANTIC and kw < MIN_KEYWORD:
                    continue
                score = max(sem, kw)
                if score > best.get(entry.specialty, (0.0, None))[0]:
                    best[entry.specialty] = (score, entry)
            for specialty in candidates:
                if specialty in best:
                    entry = best[specialty][1]
                    code = f"({entry.source.split('_')[0].upper()} {entry.code})" if entry.code else ""
                    lines.append({"phrase": phrase, "term": entry.text, "code": code, "specialty": specialty,
                                  "score": round(best[specialty][0], 3)})
        for i, line in enumerate(lines, 1):
            line["id"] = f"E{i}"
        return lines

    @staticmethod
    def build_prompt(text: str, candidates: list[str], lines: list[dict]) -> str:
        cand = "\n".join(f"- {c}: {getattr(get_specialty(c), 'description', '')}" for c in candidates)
        ev = "\n".join(f"{l['id']}: \"{l['phrase']}\" -> {l['term']} {l['code']} -> {l['specialty']}"
                       for l in lines) or "(none found)"
        return PROMPT.format(text=text.strip(), candidates=cand, evidence=ev)

    # ----------------------------------------------------------------- guards (code)
    @staticmethod
    def check(parsed: dict, candidates: list[str], lines: list[dict], text: str) -> tuple[str | None, list[str]]:
        failures = []
        choice = str(parsed.get("choice") or "").strip()
        if choice == UNCLEAR:
            return None, ["judge said unclear"]
        if choice not in candidates:
            failures.append("choice not a candidate")
        by_id = {l["id"]: l for l in lines}
        cited = [str(c) for c in parsed.get("evidence") or []]
        if not cited or any(c not in by_id for c in cited):
            failures.append("cited evidence missing or invented")
        elif not any(by_id[c]["specialty"] == choice for c in cited):
            failures.append("cited evidence does not support the choice")
        quote = str(parsed.get("patient_quote") or "")
        if not quote or not verify_phrase(quote, set(_tokens(text)))[0]:
            failures.append("quote not found in patient text")
        return (None, failures) if failures else (choice, [])

    # ----------------------------------------------------------------- the decision
    def judge(self, text: str, phrases: list[str], a: str, b: str) -> JudgeResult:
        candidates = [a, b]
        state = self.status()
        if not state["available"]:
            return JudgeResult(None, "unavailable", candidates, failures=[state.get("reason", "")])
        lines = self.evidence_lines(phrases, candidates)
        ids = [l["id"] for l in lines]
        prompts = [self.build_prompt(text, [a, b], lines), self.build_prompt(text, [b, a], lines)]
        schemas = [judge_schema([a, b], ids), judge_schema([b, a], ids)]
        futures = [self._pool.submit(self.client.generate_json, p, s, "step1_judge") for p, s in zip(prompts, schemas)]
        calls = [f.result() for f in futures]
        result = JudgeResult(None, "", candidates, evidence_lines=lines, calls=calls, prompts=prompts)
        if not all(c.ok for c in calls):
            result.status = "call failed"
            result.failures = [str(c.error)[:160] for c in calls if not c.ok]
            return result
        checked = [self.check(c.parsed, candidates, lines, text) for c in calls]
        result.choices = [c.parsed.get("choice") for c in calls]
        result.failures = sorted({f for _, fails in checked for f in fails})
        result.reason = str(calls[0].parsed.get("reason") or "")
        result.quote = str(calls[0].parsed.get("patient_quote") or "")
        if result.choices[0] != result.choices[1]:
            result.status = "order-swap flip"
        elif checked[0][0] is None:
            result.status = "unclear" if result.choices[0] == UNCLEAR else "check failed"
        else:
            result.final, result.status = checked[0][0], "accepted"
        return result
