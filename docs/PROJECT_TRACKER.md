# MediRoute – Project Tracker

State: `Done` · `In progress` · `Not started` · `Blocked` · `Deferred`

Priorities follow the TA mid-sem feedback and the capstone guidelines (see `docs/base/README.md`):
narrow scope, a strong evaluation layer with baselines, and deployment with observability.
Final review: **5 Dec 2026**. Owners are tentative.

## Readiness review (12 Nov 2026): read this first

Checked against the capstone guidelines (grading areas, final checklist) and the mid-sem TA feedback.
Full findings: **section 13 of the team report**, [docs/report/MediRoute_team_report.pdf](report/MediRoute_team_report.pdf)
(HTML: [MediRoute_team_report.html](report/MediRoute_team_report.html)).

- **Estimate:** ~70–80 / 100 today, ~82–89 if the gaps below are closed (our estimate, not the TA rubric).
- **Biggest gaps:** no deployment or monitoring dashboard; no outside users yet; no contribution or
  experiments log; ranking weights not tested (the TA asked); doctor review pending; no safety set.
- **New rows 46–56** below track them. Existing rows that cover the same work: 25 (robustness and
  weights), 29–31 (Docker, CI, dashboard), 38 (contribution log), 39 (experiments log), 40 (presentation).
- Note: several evaluation rows (19–27) predate the 11–12 Nov benchmarks and need their state updated.

## Progress (10 Nov 2026)

- **Step 1 is complete end to end:** voting pipeline (2 search voters + local LLM, majority + evidence),
  clarification form, data-correction stage (generic words dropped, 473 lay terms), per-request trace
  and an admin page. 59 tests pass; 12 Step 1 and 9 workflow API scenarios route as intended.
- **Step 1 + Step 2 integrated** in the LangGraph workflow (`/api/patient-routing`).
- **Step 2 runs** as filter → FAISS semantic search → rule-bonus rerank. AHP-TOPSIS, grounded
  explanations and the hybrid keyword retriever are not built yet. It now uses the shared hospital table.
- **Data (11 Nov):** one hospital table, `data/processed/hospitals.csv`, read by both steps: **201
  hospitals in 60 cities**, all checked against NABH, JCI and their websites (108 Verified, 36
  Partially, 57 Needs verification). The team 150 sheet adds procedures and facilities, marked "not
  verified". Every Step 1 speciality now has hospitals. Old files moved to `archive/` (see
  `archive/README.txt`).
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
| 15 | 150-hospital dataset + FAISS index | Done: Step 2 index rebuilt from `data/processed/hospitals.csv` (201 hospitals, 60 cities), the same table Step 1 reads. Every Step 1 speciality has hospitals (eye 6, ENT 8, skin 3, psychiatry 7) | Anand, Ravi | Done |
| 16 | Specialty vocabulary + ICD-10 mapping | Done for v1. Extend with task 7 and task 9 | Anand, Ravi | Done |
| 17 | JCI / NABH accreditation scraping | Done for 201 hospitals in 60 cities: the 100 team-city hospitals plus the 101 from the team 150 sheet that were not in the master, verified with the same NABH / JCI / website pipeline | Anand, Ravi | Done |
| 18 | Verified hospital-specialty data | Done: one table with per-field source (`detail_source`, `record_origin`, `team150_id`); team-sheet values marked not verified and never override accreditation. Still to do: doctor review of the 270 `draft_rule` rows in `specialty_normalization.csv`; recheck the 57 'Needs verification' hospitals (19 websites failed to load) | Anand, Ravi | In progress |
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
| **Readiness gaps (12 Nov review, see team report section 13)** | | | | |
| 46 | Cloud deployment | Deploy the API + frontend once (with Docker from row 29); keep the demo URL for the final | Aniket | Not started |
| 47 | Monitoring dashboard | p50/p95 latency per step, cost per query, error rate, success rate, one alert rule (extends row 31) | Aniket | Not started |
| 48 | CI eval gate | GitHub Actions: tests + a small Step 1 / Step 2 eval that fails if accuracy or NDCG drops (extends row 30) | Aniket | Not started |
| 49 | Ranking-weight sensitivity | Re-run the Step 2 gold set with other bonus weights (e.g. 0, half, double, no location priority); report NDCG@5 / Capable@3. TA asked for it; no LLM cost | Shubham | Not started |
| 50 | Medical suitability vs location | Decide and document: today in-area hospitals come first. Either defend it or add a "best anywhere in India" option | Shubham | Not started |
| 51 | Safety / emergency test set | 30–50 emergency and red-flag cases; report missed escalations (target 0) | Anand, Ravi | Not started |
| 52 | Report-extraction metric | For the PDF test reports: share of critical details caught (and missed) by Step 1 evidence (extends row 24) | Anand, Ravi | Not started |
| 53 | Doctor review + 20% grade spot-check | Doctor reviews ~50 Step 1 gold items and the mapping drafts; human spot-check of 20% of Step 2 grades; report agreement | Anand, Ravi | Not started |
| 54 | Outside users | 3–5 people outside the team use the portal; note what confused them (one slide) | All | Not started |
| 55 | Named versions | List of named versions (judge prompt vN, ranker vN, data vN) with dates, used in the experiments log and viva | Pravin | Not started |
| 56 | Limitations with fix paths + admin login | Each limitation in the report and deck names its fix; add the missing admin login to the list | Pravin | Not started |
| **Deferred (TA: secondary / out of core scope)** | | | | |
| 41 | CGHS cost display | Show the indicative CGHS rate per procedure. Display only, not used in ranking | TBD | Deferred |
| 42 | Translation of results | LLM translation of the final results into the patient's language | TBD | Deferred |
| 43 | PDF summary export | Downloadable PDF of the query and results | Anand | Deferred |
| 44 | Currency conversion | Convert indicative costs into the patient's currency | TBD | Deferred |
| 45 | Hospital-side enquiry agent | Agent for hospitals to track patient enquiries | TBD | Deferred |
