# MediRoute – Project Tracker

State: `Done` · `In progress` · `Not started` · `Blocked` · `Deferred`

Priorities follow the TA mid-sem feedback and the capstone guidelines (see `docs/base/README.md`):
narrow scope, a strong evaluation layer with baselines, and deployment with observability.
Final review: **5 Dec 2026**. Owners are tentative.

## Progress (10 Nov 2026)

- **Step 1 is complete end to end:** voting pipeline (2 search voters + local LLM, majority + evidence),
  clarification form, data-correction stage (generic words dropped, 473 lay terms), per-request trace
  and an admin page. 59 tests pass; 12 Step 1 and 9 workflow API scenarios route as intended.
- **Step 1 + Step 2 integrated** in the LangGraph workflow (`/api/patient-routing`).
- **Step 2 runs** as filter → FAISS semantic search → rule-bonus rerank. AHP-TOPSIS, grounded
  explanations and the hybrid keyword retriever are not built yet. It still uses the old 150-hospital
  index, so 6 specialities have no hospitals.
- **Data:** 100-hospital master verified against NABH, JCI and official websites (14 cities).
- **Biggest gap vs the TA feedback: evaluation.** Gold sets exist (Step 1), but no metrics have been
  run on the voting pipeline, no baselines, no hospital-relevance labels, no Step 2 metrics.

| # | Task | What needs to be done | Owner | State |
|---|------|-----------------------|-------|-------|
| **Step 0: Team alignment (do this first, before starting any task below)** | | | | |
| 0 | Same platform, structure and schema for everyone | Everyone pulls the `pravin` branch, creates a venv, runs `pip install -e ".[dev]"`, and starts the API and tests successfully. Walk through the project structure together (who owns which folder). Agree the shared schemas: one specialty name list, the Step 1 → Step 2 data format (`MedicalContext`), and the hospital data columns | All | Not started |
| 1 | Project structure, packaging, README | Done: `src/` layout, `pyproject.toml`, README, architecture section | Pravin | Done |
| **Step 1: Patient input → Specialty** | | | | |
| 2 | Patient query + PDF report intake | Done: `/api/analyze`, `/api/reports/parse` (PyMuPDF). Add OCR fallback only if time permits | Pravin | Done |
| 3 | Specialty routing pipeline | Done: `MEDIROUTE_ROUTING_MODE` = vote (default) / rules / llm / hybrid; router built once at startup with warm-up | Pravin | Done |
| 4 | Fix zero-shot overriding the rule result | Done: zero-shot removed from the live path; `test_blurry_vision_maps_to_ophthalmology` passes | Pravin | Done |
| 5 | Validate the LLM's answer | Done: V3 is constrained to the speciality list (JSON-schema enum) and code rejects other names | Pravin | Done |
| 6 | Extract condition with an LLM | Done as evidence extraction: LLM copies conditions, procedures, body parts. **Data correction:** code keeps only phrases found in the text and drops generic words (treatment, hospital, city, time) | Pravin | Done |
| 7 | Map to ICD-10 | Partly: lookup list of 11,057 entries = ICD-10-CM 2026 (9,314 categories) + CGHS procedures (1,270) + patient lay terms (473), mapped to specialities by draft tables (doctor review pending) | Pravin | In progress |
| 8 | Validate, else ask the user | Done: majority + evidence, else clarification form (2 rounds), then user picks; `decision` in the response | Pravin | Done |
| 9 | One shared specialty list | Done: `data/medical_taxonomy/specialties.csv` + `common/specialties.py`, used by Step 1 | Pravin | Done |
| **Step 2: Specialty → Ranked hospitals** | | | | |
| 10 | Filter hospitals by specialty and location | Done: `specialty_filter.py`, filtered FAISS | Shubham | Done |
| 11 | Hybrid retrieval (FAISS + keyword) | FAISS semantic search over the filtered hospitals is live. `keyword_retriever.py` (TF-IDF) is built but **not called by the engine**, so retrieval is not hybrid yet | Shubham | In progress |
| 12 | AHP-TOPSIS ranking | Interim: semantic score + fixed rule bonus (≤ 0.20: procedure, verified, NABH, JCI, international) in `ranking/hospital_reranker.py`. Still to do: define criteria, derive AHP weights, TOPSIS, and test the weights (medical fit must outweigh location) | Shubham | In progress |
| 13 | Grounded LLM explanation | Not built: results show rule-based `ranking_reasons` only. For each top hospital, generate a 2–3 line reason using only fields from the retrieved record; cite the fields used | Shubham | Not started |
| 14 | Connect Step 1 to Step 2 end to end | Done: `/api/patient-routing` workflow passes Step 1's speciality and evidence to the Step 2 engine; results page shows ranked hospitals (see docs/design/step1_step2_integration.md) | Shubham | Done |
| **Data** | | | | |
| 15 | 150-hospital dataset + FAISS index | 150-hospital dataset + FAISS index in use. **Rebuild the index from the 100-hospital master** (`data/processed/master-hospital-data.csv`); add eye, ENT, skin, mental-health and O&G hospitals (0 today) | Anand, Ravi | In progress |
| 16 | Specialty vocabulary + ICD-10 mapping | Done for v1. Extend with task 7 and task 9 | Anand, Ravi | Done |
| 17 | JCI / NABH accreditation scraping | Done for 100 hospitals in 14 cities: NABH certificate, JCI listing and official website checked per hospital (`data/interim/master/`) | Anand, Ravi | Done |
| 18 | Verified hospital-specialty data | 100 hospitals in `master-hospital-data.csv` with `source`, `verification_status` and `evidence_quality_score`. Still to do: merge into the Step 2 index (task 15) | Anand, Ravi | In progress |
| **Evaluation (TA: critical)** | | | | |
| 19 | Gold query set | 50 core queries in `step1_gold_core50.csv` (diagnosis, report, procedure-only, noisy, vague, CGHS gap, emergency, paediatric; with critical details) + 84 MediRoute + 212 Gretel queries. **Doctor review pending** (`step1_gold_core50_REVIEW.md`) | Anand, Ravi | In progress |
| 20 | Hospital-relevance labels | For each gold query, grade the candidate hospitals 0–3 for relevance. This is needed for NDCG | Anand, Ravi | Not started |
| 21 | Baselines | Implement 3 baselines for comparison: keyword search, rule-based specialty mapping, and specialty filter only | Anand, Ravi | Not started |
| 22 | Step 1 evaluation | `scripts/eval_step1.py` exists but evaluates the old rules / llm / hybrid routes. Update it for the voting pipeline: accuracy, top-3, clarification rate, per-voter accuracy, vs the rule baseline | Anand, Ravi | Not started |
| 23 | Step 2 evaluation | Script reports Precision@K, Recall@K and NDCG@K (K = 3, 5) for our pipeline vs the baselines | Anand, Ravi | Not started |
| 24 | Report-extraction evaluation | 20+ synthetic reports with expected fields. Measure extraction accuracy and how many critical details are missed | Anand, Ravi | Not started |
| 25 | Robustness experiments | Re-run evaluation with different ranking weights, incomplete queries and noisy reports. Record results in the experiments log | Anand, Ravi | Not started |
| 26 | LLM-as-judge | Use a different LLM to score explanation faithfulness and hallucination rate | Anand, Ravi | Not started |
| 27 | Latency and cost | Per-request timings are already in `logs/step1_trace.jsonl` (each LLM call, each voter). Still to do: p50/p95 per step and cost per query in the evaluation report | Anand, Ravi | Not started |
| **Deployment** | | | | |
| 28 | Unit and pipeline tests | 59 tests pass (Step 1 pipeline, workflow graph, Step 2). Add tests for new modules | Aniket | In progress |
| 29 | Docker | Dockerfile for the API and docker-compose (API + frontend + Ollama), with a one-command start | Aniket | Not started |
| 30 | CI | GitHub Actions running ruff + pytest on push, with an optional eval gate (accuracy must not drop) | Aniket | Not started |
| 31 | Observability dashboard | Partly: admin page (`frontend/admin.html`) shows each request's input, votes, LLM calls with timings, and the served output, from the trace log. Still to do: latency / error charts, auth | Aniket | In progress |
| 32 | LangGraph orchestration | Done: Shubham's graph ported to `backend/workflow/`, medical step replaced by the Step 1 pipeline | Aniket | Done |
| **Frontend** | | | | |
| 33 | Patient input page | Done: query + report upload | Shubham | Done |
| 34 | Results page | Show ranked hospitals with score, reason and source. Label costs as indicative | Shubham | In progress |
| 35 | Clarifying-question UI | Done: patient page shows Step 1's form and speciality list and resends with the answers | Shubham | Done |
| **Safety and process** | | | | |
| 36 | Privacy note | One-page note: synthetic data only, DPDP Act points, uploaded reports not stored, retention policy | TBD | Not started |
| 37 | Disclaimers | Show "hospital discovery, not medical advice" in the UI and API. Mark synthetic and indicative data | TBD | Not started |
| 38 | Contribution log | `docs/CONTRIBUTIONS.md`: who built and ran what, kept up weekly. Needed for the individual viva | All | Not started |
| 39 | Experiments log | `docs/EXPERIMENTS.md`: version prompts, rules and configs, one change per run, results and negative findings | All | Not started |
| 40 | Final presentation | Deck with architecture, evaluation results vs baselines, limitations slide (each with a fix path), backup demo video, rehearsal | All | Not started |
| **Deferred (TA: secondary / out of core scope)** | | | | |
| 41 | CGHS cost display | Show the indicative CGHS rate per procedure. Display only, not used in ranking | TBD | Deferred |
| 42 | Translation of results | LLM translation of the final results into the patient's language | TBD | Deferred |
| 43 | PDF summary export | Downloadable PDF of the query and results | Anand | Deferred |
| 44 | Currency conversion | Convert indicative costs into the patient's currency | TBD | Deferred |
| 45 | Hospital-side enquiry agent | Agent for hospitals to track patient enquiries | TBD | Deferred |
