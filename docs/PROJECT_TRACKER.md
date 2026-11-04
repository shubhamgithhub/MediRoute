# MediRoute – Project Tracker

State: `Done` · `In progress` · `Not started` · `Blocked` · `Deferred`

Priorities follow the TA mid-sem feedback and the capstone guidelines (see `docs/base/README.md`):
narrow scope, a strong evaluation layer with baselines, and deployment with observability.
Final review: **5 Dec 2026**. Owners are tentative.

| # | Task | What needs to be done | Owner | State |
|---|------|-----------------------|-------|-------|
| 1 | Project structure, packaging, README | Done: `src/` layout, `pyproject.toml`, README, architecture section | Pravin | Done |
| **Step 1: Patient input → Specialty** | | | | |
| 2 | Patient query + PDF report intake | Done: `/api/analyze`, `/api/reports/parse` (PyMuPDF). Add OCR fallback only if time permits | Pravin | Done |
| 3 | Specialty routing pipeline | Make each mode (rules, embeddings, LLM, zero-shot) runnable on its own with a `mode` switch. Create the router once at startup, not per request | Pravin | In progress |
| 4 | Fix zero-shot overriding the rule result | When rules match confidently, don't let a weaker zero-shot result win. Make `test_blurry_vision_maps_to_ophthalmology` pass | Pravin | Not started |
| 5 | Validate the LLM's answer | Accept the LLM's specialty only if it's in the candidate list. Otherwise fall back and set `requires_human_review` | Pravin | Not started |
| 6 | Extract condition with an LLM | Prompt the LLM to fill `MedicalContext` (symptoms, diagnoses, urgency, confidence) from query and report text. Return JSON with schema validation | Pravin | Not started |
| 7 | Map to ICD-10 | Retrieve top-k ICD-10 codes by embedding similarity, then have the LLM pick one from that list only. Expand `icd10_specialty_mapping.csv` (only 16 rows today) | Pravin | In progress |
| 8 | Validate, else ask the user | If confidence is low or the code is invalid, return a clarifying question instead of a specialty. Add `clarification_required` to the `/api/analyze` response | Pravin | In progress |
| 9 | One shared specialty list | Merge the 3 lists (router keywords, `specialty_vocabulary.csv`, `specialty_normalization.csv`) into one canonical list in `common/`. Both steps must use it | Pravin | Not started |
| **Step 2: Specialty → Ranked hospitals** | | | | |
| 10 | Filter hospitals by specialty and location | Done: `specialty_filter.py`, filtered FAISS | Shubham | Done |
| 11 | Hybrid retrieval (FAISS + keyword) | Done: FAISS index + TF-IDF keyword retriever | Shubham | Done |
| 12 | AHP-TOPSIS ranking | Define criteria (specialty match, accreditation, facilities, location), derive AHP weights, implement TOPSIS in `ranking/`. Medical fit must outweigh location | Shubham | Not started |
| 13 | Grounded LLM explanation | For each top hospital, generate a 2–3 line reason using only fields from the retrieved record. No invented facts; cite the fields used | Shubham | Not started |
| 14 | Connect Step 1 to Step 2 end to end | Convert the Step 1 result into `MedicalContext` and call `/api/hospitals/recommend`. The results page should show the ranked list instead of a location-only search | Shubham | Not started |
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
| 32 | LangGraph orchestration | Build the graph: extract → map → validate/clarify → retrieve → rank → explain, using the existing `routing_state.py` | Aniket | In progress |
| **Frontend** | | | | |
| 33 | Patient input page | Done: query + report upload | Shubham | Done |
| 34 | Results page | Show ranked hospitals with score, reason and source. Label costs as indicative | Shubham | In progress |
| 35 | Clarifying-question UI | When the API returns a clarifying question, show it and resend with the user's answer | Shubham | Not started |
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
