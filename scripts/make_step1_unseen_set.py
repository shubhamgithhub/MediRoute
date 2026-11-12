"""A brand-new Step 1 test set, written by a model that MediRoute does not use (labels by construction).

    PYTHONPATH=src python scripts/make_step1_unseen_set.py

For each of the 26 specialities we choose the speciality and the kind of message FIRST (everyday
symptoms, a named diagnosis, a procedure a doctor advised, a report snippet), then ask the writer
model for a realistic patient message that must not name the speciality. The expected answer is
therefore known by construction. 10 extra vague messages (where a good app should ask) carry the
body-area answer a patient would give and the speciality that answer should lead to.

Writes data/evaluation/step1_gold_unseen.csv (labels are DRAFT, for review like the other sets).
Cost is logged in data/evaluation/step1_unseen/generation_calls.jsonl.
"""
from __future__ import annotations

import csv
import json
import time
from pathlib import Path

from mediroute.common.specialties import load_specialties
from mediroute.specialty_routing.step1.ollama_client import OpenRouterClient
from mediroute.specialty_routing.step1.pipeline import BODY_AREAS
from mediroute.utils.paths import DATA_DIR

WRITER = "mistralai/mistral-large-4-0"
OUT = DATA_DIR / "evaluation" / "step1_gold_unseen.csv"
LOG = DATA_DIR / "evaluation" / "step1_unseen" / "generation_calls.jsonl"
KINDS = {
    "lay": "describes symptoms in everyday words only (no medical terms, no diagnosis)",
    "diagnosis": "names a diagnosis the patient was already given",
    "procedure": "says which procedure or surgery a doctor advised",
    "report": "pastes 2-3 lines from a medical report (radiology, lab or pathology style) and asks who to see",
}

PROMPT = """Write {n} different short messages that a patient (or a family member) in India might type into a
hospital-search website. Each message must be best handled by this medical speciality:

Speciality: {name}
What it covers: {desc}
Route here when: {when}
Not here: {not_here}

Message kinds, in this order: {kinds}
Rules:
- 1 to 3 sentences, realistic, varied ages and situations; one message may use simple Hinglish.
- NEVER name the speciality or the specialist (e.g. do not write "{name}" or "...ologist").
- The best speciality must clearly be the one above (stay inside "Route here when", avoid "Not here").
- "alternatives": other specialities from this list that a doctor would ALSO accept for that message
  (often none): {all_names}
- "body_area": the patient's answer to "Which part of the body is the problem in?" from: {areas}
Answer with JSON only."""

VAGUE_PROMPT = """Write 10 different VAGUE messages a patient in India might type into a hospital-search website:
too general to choose a medical speciality (e.g. "I feel weak", "need an operation", "my report is bad").
For each, also give the answer the patient would give to "Which part of the body is the problem in?"
(from: {areas}) and the speciality that answer points to (from: {all_names}).
Answer with JSON only."""

ITEM = {"type": "object", "properties": {"message": {"type": "string"}, "kind": {"type": "string"},
                                          "alternatives": {"type": "array", "items": {"type": "string"}},
                                          "body_area": {"type": "string"}},
        "required": ["message", "kind", "alternatives", "body_area"]}
SCHEMA = {"type": "object", "properties": {"messages": {"type": "array", "items": ITEM}}, "required": ["messages"]}
VAGUE_ITEM = {"type": "object", "properties": {"message": {"type": "string"}, "body_area": {"type": "string"},
                                                "specialty": {"type": "string"}},
              "required": ["message", "body_area", "specialty"]}
VAGUE_SCHEMA = {"type": "object", "properties": {"messages": {"type": "array", "items": VAGUE_ITEM}}, "required": ["messages"]}


def call(client: OpenRouterClient, prompt: str, schema: dict, tag: str) -> dict:
    for attempt in range(4):
        result = client.generate_json(prompt, schema, purpose="unseen_set_generation")
        cost = float((result.details or {}).get("cost") or 0)
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"tag": tag, "ok": result.ok, "cost": cost, "error": result.error}) + "\n")
        if result.ok:
            return result.parsed
        time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"generation failed for {tag}: {result.error}")


def main() -> None:
    client = OpenRouterClient(model=WRITER, reasoning_effort="low")  # this model rejects "reasoning off"
    specs = load_specialties()
    names = [s.name for s in specs]
    kinds = list(KINDS)
    rows = []
    for s in specs:
        n = 2 if s.name in ("Emergency Medicine", "Critical Care") else 4
        prompt = PROMPT.format(n=n, name=s.name, desc=s.description, when=s.route_here_when, not_here=s.not_here,
                               kinds="; ".join(f"{k}: {KINDS[k]}" for k in kinds[:n]), all_names="; ".join(names),
                               areas="; ".join(BODY_AREAS))
        parsed = call(client, prompt, SCHEMA, s.name)
        for i, m in enumerate(parsed.get("messages", [])[:n], 1):
            alts = [a for a in m.get("alternatives") or [] if a in names and a != s.name]
            area = m.get("body_area") if m.get("body_area") in BODY_AREAS else "Other / not sure"
            rows.append({"query_id": f"U{len(rows) + 1:03d}", "query": m["message"].strip(), "expected_specialty": s.name,
                         "acceptable_alternatives": ";".join(alts), "case_type": kinds[i - 1] if i <= len(kinds) else "lay",
                         "expects_clarification": "no", "body_area_answer": area, "source": f"generated by {WRITER}",
                         "review_status": "draft"})
        print(f"{s.name}: {n} messages", flush=True)
        time.sleep(3.3)
    vague = call(client, VAGUE_PROMPT.format(areas="; ".join(BODY_AREAS), all_names="; ".join(names)), VAGUE_SCHEMA, "vague")
    for m in vague.get("messages", [])[:10]:
        spec = m.get("specialty") if m.get("specialty") in names else "General Medicine"
        area = m.get("body_area") if m.get("body_area") in BODY_AREAS else "Other / not sure"
        rows.append({"query_id": f"U{len(rows) + 1:03d}", "query": m["message"].strip(), "expected_specialty": spec,
                     "acceptable_alternatives": "", "case_type": "vague", "expects_clarification": "yes",
                     "body_area_answer": area, "source": f"generated by {WRITER}", "review_status": "draft"})
    with OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    spent = sum(json.loads(l)["cost"] for l in LOG.read_text(encoding="utf-8").splitlines())
    print(f"{len(rows)} cases -> {OUT} · generation cost ${spent:.4f}")


if __name__ == "__main__":
    main()
