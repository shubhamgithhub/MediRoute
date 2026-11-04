# MediRoute – Project Tracker

State: `Done` · `In progress` · `Not started` · `Blocked` · `Deferred`

Plan and milestones: [PLAN.md](PLAN.md). Interfaces: [CONTRACTS.md](CONTRACTS.md).
Final review: **5 Dec 2026**. Owners are tentative. Task numbers are stable IDs; use them in PRs
and in `CONTRIBUTIONS.md`.

## M0: Plan and interfaces (due 7 Nov)

| # | Task | What needs to be done | Owner | Due | State |
|---|------|-----------------------|-------|-----|-------|
| 46 | Agree interface contracts | Review [CONTRACTS.md](CONTRACTS.md) and settle the 6 decisions listed at its end. All 5 sign off | All | 7 Nov | Not started |
| 9 | One shared specialty list | Complete `specialty_normalization.csv` (stops at "G" today) to the agreed C1 canonical list; add the `common/taxonomy.py` loader; both steps use it | Pravin | 7 Nov | Not started |
| 47 | Git workflow | Protect `main`, use feature branches per owner, require 1 reviewer per PR, add a PR template with task # and test notes | Aniket | 7 Nov | Not started |
| 38 | Contribution log | Create `docs/CONTRIBUTIONS.md` and keep it updated weekly. Needed for the individual viva | All | 7 Nov (start) | Not started |
| 39 | Experiments log | Create `docs/EXPERIMENTS.md` (template: version, change, metric before/after, notes). One change per run | All | 7 Nov (start) | Not started |

## M1: Working baseline (due 14 Nov)

| # | Task | What needs to be done | Owner | Due | State |
|---|------|-----------------------|-------|-----|-------|
| 3 | Specialty routing modes | Add a `routing_mode` switch (rules, embeddings, llm, zero_shot, hybrid) with each mode runnable on its own; create the router once at startup; return the C2 fields | Pravin | 12 Nov | In progress |
| 4 | Fix zero-shot overriding rules | A confident rule match must not lose to a weaker zero-shot result; `test_blurry_vision_maps_to_ophthalmology` passes | Pravin | 10 Nov | Not started |
| 14 | Connect Step 1 to Step 2 end to end | Use `to_medical_context()` → `/api/hospitals/recommend`; the results page shows the ranked list instead of a location-only search | Shubham | 14 Nov | Not started |
| 34 | Results page | Show ranked hospitals with score, reasons and source. Label costs as indicative | Shubham | 14 Nov | In progress |
| 19 | Gold query set v1 | 50+ queries (clear, vague, misspelled, multi-symptom, incomplete) in the C4 format with the expected specialty | Anand, Ravi | 11 Nov | Not started |
| 21 | Baselines | 3 baselines: keyword search, rule-based specialty mapping, specialty filter only | Anand, Ravi | 13 Nov | Not started |
| 22 | Step 1 evaluation script | Report specialty accuracy and top-3 accuracy per `routing_mode` on the gold set; write to `results.csv` | Anand, Ravi | 14 Nov | Not started |
| 23 | Step 2 evaluation script | Report Precision@K and Recall@K (K = 3, 5) for our pipeline vs the baselines. Add NDCG once task 20 is done | Anand, Ravi | 14 Nov | Not started |
| 18 | Verified hospital-specialty data | Verify specialties from official websites; add `source` and `is_synthetic`; merge into the master using C1 names | Anand, Ravi | 14 Nov | In progress |
| 29 | Docker | Dockerfile for the API and docker-compose (API + frontend + Ollama), with a one-command start | Aniket | 14 Nov | Not started |
| 28 | Unit and pipeline tests | Keep `pytest` green; add tests for new modules | Aniket | ongoing | In progress |

## M2: Improve and measure (due 22 Nov)

| # | Task | What needs to be done | Owner | Due | State |
|---|------|-----------------------|-------|-----|-------|
| 5 | Validate the LLM's answer | Accept the LLM's specialty only if it's in the candidate list; otherwise fall back and set `requires_human_review` | Pravin | 17 Nov | Not started |
| 7 | Map to ICD-10 | Retrieve top-k ICD-10 codes, then the LLM picks one from that list only; expand `icd10_specialty_mapping.csv` (16 rows today) | Pravin | 20 Nov | In progress |
| 6 | Extract condition with an LLM | The LLM fills `MedicalContext` (symptoms, diagnoses, urgency, confidence) from query and report text, as JSON with schema validation | Pravin | 21 Nov | Not started |
| 8 | Validate, else ask the user | Low confidence or an invalid code → return `clarification_question` instead of a specialty | Pravin | 22 Nov | In progress |
| 12 | AHP-TOPSIS ranking | Criteria (specialty match, accreditation, facilities, location), AHP weights, TOPSIS in `ranking/`, `score_breakdown` in the output. Medical fit outweighs location | Shubham | 20 Nov | Not started |
| 13 | Grounded LLM explanation | A 2–3 line reason per hospital using only fields from its record; cite the fields used | Shubham | 22 Nov | Not started |
| 35 | Clarifying-question UI | When the API returns `clarification_question`, show it and resend with the user's answer | Shubham | 22 Nov | Not started |
| 20 | Hospital-relevance labels | Grade candidate hospitals 0–3 per gold query (C4 definitions); enables NDCG@K | Anand, Ravi | 18 Nov | Not started |
| 24 | Report-extraction evaluation | 20+ synthetic reports with expected fields; measure extraction accuracy and missed critical details | Anand, Ravi | 22 Nov | Not started |
| 17 | JCI / NABH accreditation scraping | Finish the remaining target cities; rebuild the FAISS index on the final master | Anand, Ravi | 20 Nov | In progress |
| 30 | CI | GitHub Actions: ruff + pytest on every PR, plus an optional eval gate (accuracy must not drop) | Aniket | 18 Nov | Not started |
| 32 | LangGraph orchestration | Graph: extract → map → validate/clarify → retrieve → rank → explain, using `routing_state.py` | Aniket | 22 Nov | In progress |
| 36 | Privacy note | One page: synthetic data only, DPDP Act points, uploaded reports not stored, retention policy | Anand | 22 Nov | Not started |
| 37 | Disclaimers | "Hospital discovery, not medical advice" in UI and API; mark synthetic and indicative data | Shubham | 22 Nov | Not started |

## M3: Hardening (due 29 Nov, feature freeze)

| # | Task | What needs to be done | Owner | Due | State |
|---|------|-----------------------|-------|-----|-------|
| 25 | Robustness experiments | Re-run the evaluation with different ranking weights, incomplete queries and noisy reports; log the results in EXPERIMENTS.md | Anand, Ravi | 27 Nov | Not started |
| 26 | LLM-as-judge | A different LLM scores explanation faithfulness and hallucination rate | Anand, Ravi | 27 Nov | Not started |
| 27 | Latency and cost | p50/p95 latency per step and LLM cost per query, in the evaluation results | Anand, Ravi | 28 Nov | Not started |
| 31 | Observability dashboard | Latency, cost and errors per step from the request logs (C5); Grafana or a Streamlit page | Aniket | 29 Nov | Not started |
| 48 | Outside user test | Someone outside the team uses the system; note the feedback (final checklist item) | All | 29 Nov | Not started |

## M4: Final (due 5 Dec, code freeze 2 Dec)

| # | Task | What needs to be done | Owner | Due | State |
|---|------|-----------------------|-------|-----|-------|
| 49 | Final report | Project report: problem, architecture, evaluation results vs baselines, limitations with fix paths | Anand | 3 Dec | Not started |
| 40 | Final presentation | Deck, limitations slide, backup demo recording, 2 rehearsals within 20 minutes | All | 4 Dec | Not started |

## Done

| # | Task | What exists | Owner | State |
|---|------|-------------|-------|-------|
| 1 | Project structure, packaging, README | `src/` layout, `pyproject.toml`, README, two-step package split | Pravin | Done |
| 2 | Patient query + PDF report intake | `/api/analyze`, `/api/reports/parse` (PyMuPDF) | Pravin | Done |
| 10 | Filter hospitals by specialty and location | `specialty_filter.py`, filtered FAISS | Shubham | Done |
| 11 | Hybrid retrieval (FAISS + keyword) | FAISS index + TF-IDF keyword retriever | Shubham | Done |
| 15 | 150-hospital dataset + FAISS index | Rebuild when the master data is final (task 17) | Anand, Ravi | Done |
| 16 | Specialty vocabulary + ICD-10 mapping v1 | Extended by tasks 7 and 9 | Anand, Ravi | Done |
| 33 | Patient input page | Query + report upload | Shubham | Done |

## Deferred (TA: secondary / out of core scope)

| # | Task | What needs to be done | Owner | State |
|---|------|-----------------------|-------|-------|
| 41 | CGHS cost display | Indicative CGHS rate per procedure; display only, not ranked | TBD | Deferred |
| 42 | Translation of results | LLM translation of the final results | TBD | Deferred |
| 43 | PDF summary export | Downloadable PDF of the query and results | Anand | Deferred |
| 44 | Currency conversion | Convert indicative costs to the patient's currency | TBD | Deferred |
| 45 | Hospital-side enquiry agent | Agent for hospitals to track enquiries | TBD | Deferred |
