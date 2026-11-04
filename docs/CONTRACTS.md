# MediRoute – Interface Contracts (M0 draft, for team review)

**Status: DRAFT.** All 5 members review and agree this by **7 Nov**. After that, changes
need a PR approved by the owners on both sides of the interface.

These contracts let Step 1, Step 2, data, evaluation and frontend work proceed in parallel.

---

## C1. Canonical specialty list (shared by everyone)

**Problem today:** there are three specialty lists, and they don't agree.

| Where | Count | Used by |
|-------|-------|---------|
| `SPECIALTY_KEYWORDS` in `specialty_routing/router.py` | 16 | Step 1 rules |
| `data/medical_taxonomy/specialty_vocabulary.csv` | 88 raw hospital labels | Step 1 embedding candidates |
| `data/medical_taxonomy/specialty_normalization.csv` | 31 rows → **13 canonical** | Step 2 filter, hospital master `verified_specialties` |

`specialty_normalization.csv` stops at "Gastro Sciences", so it covers only part of the
alphabet. As a result, **10 of the 16 specialties Step 1 can output have no match in Step 2**:
Neurology, Nephrology, Urology, Pulmonology, Ophthalmology, ENT, Dermatology, Obstetrics &
Gynecology, Psychiatry and General Medicine.

**Proposal:**
- **One source of truth:** the `canonical_specialty` column of `specialty_normalization.csv`,
  completed to cover every raw label in the dataset.
- **Rule 1:** Step 1 may only output a specialty from this list.
- **Rule 2:** Step 2 filters only on this list.
- **Rule 3:** the hospital master's `verified_specialties` column uses only this list. This
  already matches `hospital.schema.csv`.
- **Rule 4:** load the list through one helper (`mediroute.common.taxonomy`). Don't hard-code
  specialty names in code.

**Proposed canonical routing targets (24).** Agree, add or remove:

| Area | Canonical specialties |
|------|-----------------------|
| Heart | Cardiology · Cardiothoracic Surgery · Pediatric Cardiology |
| Cancer & blood | Oncology · Hematology & Bone Marrow Transplant |
| Bones & nerves | Orthopaedics · Neurology · Neurosurgery |
| Organs | Gastroenterology · Hepatology & Liver Transplant · Nephrology · Urology · Pulmonology · Endocrinology |
| Women & children | Obstetrics & Gynecology · Reproductive Medicine · Pediatrics |
| Other | Ophthalmology · ENT · Dermatology · Psychiatry · Plastic & Reconstructive Surgery · Bariatric Surgery · General Medicine |

**Services, not routing targets:** Emergency Medicine, Critical Care, Rehabilitation,
Palliative Care, Interventional Radiology and Robotic Surgery. Hospitals can list them, but
Step 1 never routes a patient to them.

Owners: Pravin (Step 1 side), Anand and Ravi (data side). Shubham confirms the Step 2 filter.

---

## C2. Step 1 output: `POST /api/analyze` → `medicalContext`

Keep the current fields so the frontend doesn't break, and **add** the fields marked *new*.

```json
{
  "relevantSpecialty": "Ophthalmology",          // MUST be a C1 canonical specialty
  "careCategory": "Eye Care",
  "confidence": 0.82,                              // 0–1
  "reasoning": ["Matched symptom keywords: vision"],
  "matched_terms": ["vision"],
  "requires_human_review": false,
  "alternativeSpecialties": ["Neurology"],         // new: ranked runners-up (canonical)
  "icd10_codes": ["H53.8"],                        // new: may be empty until the ICD-10 task is done
  "clarification_question": null,                  // new: set when the system needs to ask the user
  "routing_mode": "rules",                         // new: rules | embeddings | llm | zero_shot | hybrid
  "router_version": "router-v1-rules"              // new: for experiments and logs
}
```

**Conversion to Step 2:** Step 1 provides `to_medical_context()`, so the frontend and the
API never map fields by hand.

| Step 1 field | `MedicalContext` field |
|--------------|------------------------|
| `relevantSpecialty` | `primary_specialty` |
| `[relevantSpecialty] + alternativeSpecialties` | `canonical_specialties` |
| `icd10_codes` | `icd10_codes` |
| `matched_terms` | `symptoms` |
| `requires_human_review` or `clarification_question` | `clarification_required` |

---

## C3. Step 2 input and output: `POST /api/hospitals/recommend`

**Input (exists today):**
```json
{ "context": { /* MedicalContext */ }, "preferred_city": "Chennai", "preferred_state": null, "top_k": 5 }
```

**Output:** keep the current envelope (`status`, `primary_specialty`, `count`, `results`, …).
Each item in `results` **must** contain:

| Field | Type | Notes |
|-------|------|-------|
| `hospital_id` | string | Same ID as in the hospital master (`H###`). Evaluation joins on this |
| `hospital_name`, `city`, `state` | string | |
| `final_rank` | int | 1 = best |
| `final_score` | float | 0–1 after AHP-TOPSIS |
| `score_breakdown` | object | *new*: one entry per criterion, e.g. `{"specialty_match": 0.9, "accreditation": 1.0, "location": 0.5}` |
| `ranking_reasons` | list[str] | Deterministic reasons |
| `explanation` | string | *new (M2)*: LLM text grounded only in this record |
| `sources` | list[str] | *new*: evidence URLs (official site, NABH, JCI) |
| `is_synthetic` | bool | *new*: true if any field used for ranking is synthetic |

`status` values: `success`, `needs_clarification`, `no_specialty_match`, `no_location_match`.

---

## C4. Evaluation data formats (owners: Anand, Ravi)

Location: `data/evaluation/`

**`gold_queries.csv`:** one row per test query.

| Column | Example | Notes |
|--------|---------|-------|
| `query_id` | Q001 | |
| `query_text` | "my vision is blurry since 2 weeks" | |
| `query_type` | clear | clear · vague · misspelled · multi_symptom · incomplete · report |
| `expected_specialty` | Ophthalmology | C1 canonical |
| `acceptable_specialties` | Neurology | Semicolon list. These also count as correct |
| `expected_icd10` | H53.8 | Optional |
| `urgency` | routine | routine · urgent · emergency |
| `preferred_city` | Chennai | Optional |
| `reviewed_by` | Dr X / team | Who checked the label |

**`relevance_labels.csv`:** graded hospital relevance per query, used for NDCG.

| Column | Notes |
|--------|-------|
| `query_id`, `hospital_id` | |
| `relevance` | 3 = verified specialty + accredited + right city; 2 = verified specialty, other city; 1 = related specialty; 0 = not suitable |
| `labeler`, `notes` | |

**Evaluation results:** each run appends one row to `data/evaluation/results.csv`:
`run_id, date, component, version, metric, k, value, n_queries, notes`.

---

## C5. Versioning and logging

- **Version names:**
  - Step 1 sets `router_version`; Step 2 sets `ranker_version`.
  - Prompts are stored in files (`prompts/<name>_v<N>.txt`), not inline strings.
  - Ranking weights are stored in config (`weights_v<N>`).
- **Per-request logging:** every API call logs `request_id`, `step`, `latency_ms`,
  `llm_tokens`, `cost_estimate` and `error`. The observability dashboard reads these
  (owner: Aniket).

---

## Decisions needed at the M0 meeting

1. Approve the C1 canonical list (24 targets + services).
2. Approve the new Step 1 fields (C2) and the Step 2 result fields (C3).
3. Approve the gold-set and relevance-label formats (C4), including the 0–3 grade definitions.
4. Medical reviewer: can anyone get a doctor to review the gold set and the diagnosis-to-specialty mapping?
5. Hosted LLM for final evaluation runs and the judge model (budget ₹40k). Local Ollama for development.
6. Branch naming and the PR review rule (see PLAN.md).
