# MediRoute – Project Tracker

State: `Done` · `In progress` · `Not started` · `Blocked` · `Deferred`

Priorities follow the TA mid-sem feedback and the capstone guidelines (see `docs/base/README.md`):
narrow scope, a strong evaluation layer with baselines, and deployment with observability.
Final review: **5 Dec 2026**.

| # | Task | Owner | State |
|---|------|-------|-------|
| 1 | Project structure, packaging, README | Pravin | Done |
| **Step 1: Patient input → Specialty** | | | |
| 2 | Patient query + PDF report intake | TBD | Done |
| 3 | Specialty routing (rules → embeddings → LLM → zero-shot) | Pravin | In progress |
| 4 | Fix: zero-shot overrides correct rule result (blurry vision → "Liver Care") | Pravin | Not started |
| 5 | Validate the LLM's answer against the candidate list | Pravin | Not started |
| 6 | Extract condition with LLM (symptoms, urgency, confidence) | TBD | Not started |
| 7 | Map to ICD-10 (retrieve, then LLM picks) | TBD | In progress |
| 8 | Validate, else ask user a clarifying question | TBD | In progress |
| 9 | One shared specialty list for Step 1 and Step 2 | TBD | Not started |
| **Step 2: Specialty → Ranked hospitals** | | | |
| 10 | Filter hospitals by specialty and location | TBD | Done |
| 11 | Hybrid retrieval (FAISS + keyword) | TBD | Done |
| 12 | AHP-TOPSIS ranking (medical fit ahead of location) | TBD | Not started |
| 13 | Grounded LLM explanation (from retrieved records only) | TBD | Not started |
| 14 | Connect Step 1 output to Step 2 end to end (API + results page) | TBD | Not started |
| **Data** | | | |
| 15 | 150-hospital dataset + FAISS index | TBD | Done |
| 16 | Specialty vocabulary + ICD-10 mapping | TBD | Done |
| 17 | JCI / NABH accreditation scraping | TBD | In progress |
| 18 | Verified hospital-specialty data, real vs synthetic clearly marked | TBD | In progress |
| **Evaluation (TA: critical)** | | | |
| 19 | Gold set: labelled patient queries → expected specialty (≥ 50) | TBD | Not started |
| 20 | Graded hospital-relevance labels for the gold queries | TBD | Not started |
| 21 | Baselines: keyword search, rule-based mapping, specialty filter | TBD | Not started |
| 22 | Step 1 metric: specialty accuracy vs rule baseline | TBD | Not started |
| 23 | Step 2 metrics: Precision@K, Recall@K, NDCG@K vs baselines | TBD | Not started |
| 24 | Extraction accuracy + omission of critical details (reports) | TBD | Not started |
| 25 | Experiments: ranking weights, incomplete queries, noisy reports | TBD | Not started |
| 26 | LLM-as-judge (different model) for explanation faithfulness | TBD | Not started |
| 27 | Latency and cost per query | TBD | Not started |
| **Deployment** | | | |
| 28 | Unit and pipeline tests | TBD | In progress |
| 29 | Dockerfile + docker-compose | TBD | Not started |
| 30 | CI: lint + tests (+ eval gate) on push | TBD | Not started |
| 31 | Observability dashboard: latency, cost, errors per step | TBD | Not started |
| 32 | LangGraph orchestration (Step 1 → Step 2) | TBD | In progress |
| **Frontend** | | | |
| 33 | Patient input page | TBD | Done |
| 34 | Results page (ranking, explanation) | TBD | In progress |
| 35 | Clarifying-question UI | TBD | Not started |
| **Safety and process** | | | |
| 36 | Privacy note: synthetic data only, DPDP Act, report handling | TBD | Not started |
| 37 | Disclaimers: discovery, not medical advice; costs indicative | TBD | Not started |
| 38 | Contribution log (who did what), needed for the viva | All | Not started |
| 39 | Experiments log (versioned prompts, rules, configs) | All | Not started |
| 40 | Final deck: limitations slide, backup demo recording | All | Not started |
| **Deferred (TA: secondary / out of core scope)** | | | |
| 41 | CGHS cost display | TBD | Deferred |
| 42 | Translation of results | TBD | Deferred |
| 43 | PDF summary export | TBD | Deferred |
| 44 | Currency conversion | TBD | Deferred |
| 45 | Hospital-side enquiry agent | TBD | Deferred |
