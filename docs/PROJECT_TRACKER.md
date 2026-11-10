# MediRoute – Project Tracker

State: `Done` · `In progress` · `Not started` · `Blocked` · `Deferred`

Priorities follow the TA mid-sem feedback and the capstone guidelines (see `docs/base/README.md`):
narrow scope, a strong evaluation layer with baselines, and deployment with observability.
Final review: **5 Dec 2026**. Owners are tentative.

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
| 6 | Extract condition with an LLM | Done as evidence extraction: LLM copies conditions, procedures, body parts; code keeps only phrases found in the text | Pravin | Done |
| 7 | Map to ICD-10 | Partly: ICD-10-CM 2026 (9,314 categories) + CGHS procedures mapped to specialities in the Step 1 lookup list (draft tables, doctor review pending) | Pravin | In progress |
| 8 | Validate, else ask the user | Done: majority + evidence, else clarification form (2 rounds), then user picks; `decision` in the response | Pravin | Done |
| 9 | One shared specialty list | Done: `data/medical_taxonomy/specialties.csv` + `common/specialties.py`, used by Step 1 | Pravin | Done |
| **Step 2: Specialty → Ranked hospitals** | | | | |
| 10 | Filter hospitals by specialty and location | Done: `specialty_filter.py`, filtered FAISS | Shubham | Done |
| 11 | Hybrid retrieval (FAISS + keyword) | Done: FAISS index + TF-IDF keyword retriever | Shubham | Done |
| 12 | AHP-TOPSIS ranking | Define criteria (specialty match, accreditation, facilities, location), derive AHP weights, implement TOPSIS in `ranking/`. Medical fit must outweigh location | Shubham | Not started |
| 13 | Grounded LLM explanation | For each top hospital, generate a 2–3 line reason using only fields from the retrieved record. No invented facts; cite the fields used | Shubham | Not started |
| 14 | Connect Step 1 to Step 2 end to end | Done: `/api/patient-routing` workflow passes Step 1's speciality and evidence to the Step 2 engine; results page shows ranked hospitals (see docs/design/step1_step2_integration.md) | Shubham | Done |
| **Data** | | | | |
| 15 | 150-hospital dataset + FAISS index | Done. Rebuild the index when the new master data is final | Anand, Ravi | Done |
| 16 | Specialty vocabulary + ICD-10 mapping | Done for v1. Extend with task 7 and task 9 | Anand, Ravi | Done |
| 17 | JCI / NABH accreditation scraping | Finish the remaining target cities and save outputs in `data/interim/` | Anand, Ravi | In progress |
| 18 | Verified hospital-specialty data | Verify each hospital's specialties from its official website. Add `source` and `is_synthetic` columns, and merge into the master dataset | Anand, Ravi | In progress |
| **Evaluation (TA: critical)** | | | | |
| 19 | Gold query set | 50+ patient queries (clear, vague, misspelled, multi-symptom) with the expected specialty. Get it reviewed by a doctor if possible | Anand, Ravi | Not started |
| 20 | Hospital-relevance labels | For each gold query, grade the candidate hospitals 0–3 for relevance. This is needed for NDCG | Anand, Ravi | Not started |
| 21 | Baselines | Implement 3 baselines for comparison: keyword search, rule-based specialty mapping, and specialty filter only | Anand, Ravi | Not started |
| 22 | Step 1 evaluation | Script reports specialty accuracy and top-3 accuracy for each router mode vs the rule baseline on the gold set | Anand, Ravi | Not started |
| 23 | Step 2 evaluation | Script reports Precision@K, Recall@K and NDCG@K (K = 3, 5) for our pipeline vs the baselines | Anand, Ravi | Not started |
| 24 | Report-extraction evaluation | 20+ synthetic reports with expected fields. Measure extraction accuracy and how many critical details are missed | Anand, Ravi | Not started |
| 25 | Robustness experiments | Re-run evaluation with different ranking weights, incomplete queries and noisy reports. Record results in the experiments log | Anand, Ravi | Not started |
| 26 | LLM-as-judge | Use a different LLM to score explanation faithfulness and hallucination rate | Anand, Ravi | Not started |
| 27 | Latency and cost | Measure p50/p95 latency per step and LLM cost per query, and report them in the evaluation results | Anand, Ravi | Not started |
| **Deployment** | | | | |
| 28 | Unit and pipeline tests | Keep `pytest` green and add tests for new modules. One test fails today (task 4) | Aniket | In progress |
| 29 | Docker | Dockerfile for the API and docker-compose (API + frontend + Ollama), with a one-command start | Aniket | Not started |
| 30 | CI | GitHub Actions running ruff + pytest on push, with an optional eval gate (accuracy must not drop) | Aniket | Not started |
| 31 | Observability dashboard | Log latency, cost and errors per pipeline step. Show them on a dashboard (Grafana or a simple Streamlit page) | Aniket | Not started |
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
