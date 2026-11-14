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
  experiments log; doctor review pending; no safety set. (Ranking weights and report extraction,
  both asked by the TA, were tested on 13 Nov: rows 49 and 52.)
- **New rows 46–56** below track them. Existing rows that cover the same work: 25 (robustness and
  weights), 29–31 (Docker, CI, dashboard), 38 (contribution log), 39 (experiments log), 40 (presentation).
- 13 Nov: evaluation rows 19–25 and 27 updated to Done from the 11–13 Nov benchmarks (report sections 7, 8, 8c);
  row 26 waits for row 13.

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
| 19 | Gold query set | Done: Step 1: 50 core queries in `step1_gold_core50.csv` + 84 MediRoute + 212 Gretel + 110 unseen portal messages; Step 2: 45 requests in `step2_gold.csv`. Doctor review of the labels is row 53 | Anand, Ravi | Done |
| 20 | Hospital-relevance labels | Done: `step2_capability_grades.csv` grades candidate hospitals 0–3 for each of the 45 Step 2 requests (894 grades, from hospital websites); used for NDCG. 20% human spot-check is row 53 | Anand, Ravi | Done |
| 21 | Baselines | Done: Step 1: keyword search (TF-IDF), semantic search, LLM only, most-common floor (`benchmark_step1.py`); Step 2: keyword search, specialty filter only, random and ablations (`eval_step2.py`). Report sections 7 and 8 | Anand, Ravi | Done |
| 22 | Step 1 evaluation | Done: `scripts/benchmark_step1.py` evaluates the voting pipeline: accuracy with 95% CI, Recall@3, NDCG@3, macro-F1, confidently wrong, ask rate, McNemar vs each baseline; plus unseen and portal runs. Report section 7 | Anand, Ravi | Done |
| 23 | Step 2 evaluation | Done: `scripts/eval_step2.py` reports P@K, R@K, NDCG@K (K = 3, 5), Capable@3, Bad@3 vs the baselines with bootstrap CI and permutation tests. NDCG@5 0.807 (judged-only). Report section 8 | Anand, Ravi | Done |
| 24 | Report-extraction evaluation | Done 13 Nov: 23 PDF reports (15 clean + 8 layout cases), 85 critical details, accuracy and omissions at 3 levels (`scripts/eval_report_extraction.py`). Report section 8c.1; see row 52 | Anand, Ravi | Done |
| 25 | Robustness experiments | Done: ranking weights (13 variants, section 8c.2), incomplete / vague queries (unseen set, right outcome 94%, section 7b), noisy reports (8 layout cases, section 8c.1). Writing them into the experiments log is row 39 | Anand, Ravi | Done |
| 26 | LLM-as-judge | Not possible yet: needs the grounded explanations from row 13. (An LLM judge is already used for Step 1 disagreements and for Step 2 capability grading, but not for explanation faithfulness) | Anand, Ravi | Not started |
| 27 | Latency and cost | Done: p50 / p95 per step from `logs/step1_trace.jsonl` (p95 6.5 s with GPT-6 Luna) and cost per query are in the team report (Cost section) | Anand, Ravi | Done |
| **Deployment** | | | | |
| 28 | Unit and pipeline tests | 133 tests pass (13 Nov: Step 1 pipeline, provider default, workflow graph, Step 2). Keep adding tests for new modules | Aniket | In progress |
| 29 | Docker | Dockerfile for the API and docker-compose (API + frontend + Ollama), with a one-command start | Aniket | Not started |
| 30 | CI | GitHub Actions running ruff + pytest on push, with an optional eval gate (accuracy must not drop) | Aniket | Not started |
| 31 | Observability dashboard | Partly: admin page (`frontend/admin.html`) shows each request's input, votes, LLM calls with timings, the Step 1 algorithms (weights, scores, decision rule) and how Step 2 ranked the hospitals, newest 100 requests. Still to do: latency / error charts, auth (rows 47, 56) | Aniket | In progress |
| 32 | LangGraph orchestration | Done: Shubham's graph ported to `backend/workflow/`, medical step replaced by the Step 1 pipeline | Aniket | Done |
| **Frontend** | | | | |
| 33 | Patient input page | Done: query + report upload | Shubham | Done |
| 34 | Results page | Show ranked hospitals with score, reason and source. Label costs as indicative | Shubham | In progress |
| 35 | Clarifying-question UI | Done: patient page shows Step 1's form and speciality list and resends with the answers | Shubham | Done |
| **Safety and process** | | | | |
| 36 | Privacy note | One-page note: synthetic data only, DPDP Act points, uploaded reports not stored, retention policy | TBD | Not started |
| 37 | Disclaimers | Done: "hospital discovery, not medical advice" shown on the patient, home and hospital pages and returned as `disclaimer` by the API. Costs are deferred (row 41), so no indicative-cost label is needed yet | TBD | Done |
| 38 | Contribution log | `docs/CONTRIBUTIONS.md`: who built and ran what, kept up weekly. Needed for the individual viva | All | Not started |
| 39 | Experiments log | `docs/EXPERIMENTS.md`: version prompts, rules and configs, one change per run, results and negative findings | All | Not started |
| 40 | Final presentation | Deck with architecture, evaluation results vs baselines, limitations slide (each with a fix path), backup demo video, rehearsal | All | Not started |
| **Readiness gaps (12 Nov review, see team report section 13)** | | | | |
| 46 | Cloud deployment | Deploy the API + frontend once (with Docker from row 29); keep the demo URL for the final | Aniket | Not started |
| 47 | Monitoring dashboard | p50/p95 latency per step, cost per query, error rate, success rate, one alert rule (extends row 31) | Aniket | Not started |
| 48 | CI eval gate | GitHub Actions: tests + a small Step 1 / Step 2 eval that fails if accuracy or NDCG drops (extends row 30) | Aniket | Not started |
| 49 | Ranking-weight sensitivity | Re-run the Step 2 gold set with other bonus weights (e.g. 0, half, double, no location priority); report NDCG@5 / Capable@3. TA asked for it; no LLM cost | Shubham | Done 13 Nov: bonuses help (p = 0.02), exact values within noise; report section 8c.2, scripts/eval_step2_weights.py |
| 50 | Medical suitability vs location | Decide and document: today in-area hospitals come first. Either defend it or add a "best anywhere in India" option | Shubham | Not started |
| 51 | Safety / emergency test set | 30–50 emergency and red-flag cases; report missed escalations (target 0). Partly 14 Nov: red-flag rules extended (chest pain with breathlessness / racing heart / dizziness, loss of sight, confusion) → Emergency Medicine; all 10 gretel red-flag messages caught, no false alarm on core50 / mediroute / unseen (report 7c). Still to do: a dedicated set | Anand, Ravi | In progress |
| 52 | Report-extraction metric | For the PDF test reports: share of critical details caught (and missed) by Step 1 evidence (extends row 24) | Anand, Ravi | Done 13 Nov: 93% of 85 critical details kept (94% decisive); only miss = long report cut at 6,000 chars; report section 8c.1, scripts/eval_report_extraction.py. Labels need doctor review |
| 53 | Doctor review + 20% grade spot-check | Doctor reviews ~50 Step 1 gold items and the mapping drafts; human spot-check of 20% of Step 2 grades; report agreement. Ready for the doctor (14 Nov): gretel labelling rule + 100 rows (`data/evaluation/step1_gold_gretel_rule_review.csv`), body-area files (`data/processed/body_area_tags.csv`, `body_area_neighbours.csv`), varicose-veins mapping conflict (Cardiology vs Cardiothoracic Surgery) | Anand, Ravi | Not started |
| 54 | Outside users | 3–5 people outside the team use the portal; note what confused them (one slide) | All | Not started |
| 55 | Named versions | List of named versions (judge prompt vN, ranker vN, data vN) with dates, used in the experiments log and viva | Pravin | Not started |
| 56 | Limitations with fix paths + admin login | Each limitation in the report and deck names its fix; add the missing admin login to the list | Pravin | Not started |
| **Deferred (TA: secondary / out of core scope)** | | | | |
| 41 | CGHS cost display | Show the indicative CGHS rate per procedure. Display only, not used in ranking | TBD | Deferred |
| 42 | Translation of results | LLM translation of the final results into the patient's language | TBD | Deferred |
| 43 | PDF summary export | Downloadable PDF of the query and results | Anand | Deferred |
| 44 | Currency conversion | Convert indicative costs into the patient's currency | TBD | Deferred |
| 45 | Hospital-side enquiry agent | Agent for hospitals to track patient enquiries | TBD | Deferred |
