# MediRoute – Project Tracker

State: `Done` · `In progress` · `Not started` · `Blocked`

| # | Task | Owner | State |
|---|------|-------|-------|
| 1 | Project structure, packaging, README | Pravin | Done |
| **Step 1: Patient input → Specialty** | | | |
| 2 | Patient query + PDF report intake | TBD | Done |
| 3 | Specialty routing (rules → embeddings → LLM → zero-shot) | Pravin | In progress |
| 4 | Fix: zero-shot overrides correct rule result (blurry vision → "Liver Care") | Pravin | Not started |
| 5 | Extract condition with LLM (symptoms, urgency, confidence) | TBD | Not started |
| 6 | Map to ICD-10 (retrieve, then LLM picks) | TBD | In progress |
| 7 | Validate, else ask user a clarifying question | TBD | In progress |
| 8 | Specialty → treatment + CGHS procedure candidates | TBD | Not started |
| 9 | One shared specialty list for Step 1 and Step 2 | TBD | Not started |
| **Step 2: Specialty → Ranked hospitals** | | | |
| 10 | Filter hospitals by specialty and location | TBD | Done |
| 11 | Hybrid retrieval (FAISS + keyword) | TBD | Done |
| 12 | AHP weights (expert criteria) | TBD | Not started |
| 13 | TOPSIS ranking | TBD | Not started |
| 14 | Grounded LLM explanation | TBD | Not started |
| 15 | CGHS cost display | TBD | Not started |
| 16 | Translation + PDF export | TBD | Not started |
| **Data** | | | |
| 17 | 150-hospital dataset + FAISS index | TBD | Done |
| 18 | Specialty vocabulary + ICD-10 mapping | TBD | Done |
| 19 | JCI / NABH accreditation scraping | TBD | In progress |
| 20 | Hospital master for all target cities | TBD | In progress |
| **Frontend** | | | |
| 21 | Patient input page | TBD | Done |
| 22 | Results page (ranking, explanation, cost) | TBD | In progress |
| 23 | Connect results page to Step 2 recommendations | TBD | Not started |
| 24 | Clarifying-question UI | TBD | Not started |
| **Integration & Evaluation** | | | |
| 25 | LangGraph orchestration (Step 1 → Step 2) | TBD | In progress |
| 26 | Unit and pipeline tests | TBD | In progress |
| 27 | Evaluation vs baselines (Step 1 accuracy, Step 2 ranking) | TBD | Not started |
| 28 | CI: lint + tests on push | TBD | Not started |
