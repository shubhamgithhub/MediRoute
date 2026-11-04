# MediRoute

**AI-assisted patient-to-hospital routing.** A patient describes their problem in plain language
(and can upload medical reports as PDFs). MediRoute works out the likely condition, the medical
specialty and the treatment needed, then recommends a **ranked, explained list of accredited
hospitals** with indicative costs.

> Capstone project, PG Program in AI/ML in Practice, IIT Bombay.

---

## 1. What problem does it solve?

People who need specialist care, such as medical travellers and patients from smaller cities, often
don't know **which specialty** they need or **which hospital** is actually equipped for it. Today
this matching is done by human coordinators (Bookimed, Medmonks) or by opaque "AI matching" tools
that publish no evaluation.

MediRoute aims to be:

- **Accurate.** Language understanding comes from an LLM and embeddings, constrained to a fixed
  ICD-10 list and checked by code.
- **Transparent.** Hospitals are ranked by a deterministic, explainable method (AHP-TOPSIS), not
  by the LLM.
- **Grounded.** The LLM only *explains* results using the retrieved hospital records, so it can't
  invent hospitals.

## 2. Architecture

![MediRoute two-step pipeline](docs/architecture/mediroute_pipeline_architecture.png)

The pipeline has two steps. Each box is either an **LLM/embedding** component (purple),
**deterministic code** (green) or **input data** (grey).

### Step 1: Patient input to specialty and treatment

| # | Stage | What it does | Type |
|---|-------|--------------|------|
| 1.1 | **Extract condition** | Pull symptoms, urgency and a confidence score from the query and report text | LLM / embeddings |
| 1.2 | **Map to ICD-10 code** | Retrieve candidate codes from the ICD-10 list, then the LLM picks one | LLM + retrieval |
| 1.3 | **Validate, else ask user** | Check the code exists and confidence is above threshold. Otherwise ask a clarifying question | Code |
| 1.4 | **Specialty and treatment** | ICD-10 code to specialty, plus candidate CGHS procedures | Code |

### Step 2: Specialty to ranked hospitals

| # | Stage | What it does | Type |
|---|-------|--------------|------|
| 2.1 | **Filter hospitals** | Keep only NABH hospitals offering the required specialty, near the preferred location | Code |
| 2.2 | **AHP weights + TOPSIS rank** | Score hospitals on expert-weighted criteria (staff, equipment, accreditation) | Code |
| 2.3 | **Write explanation** | Explain the ranking using **only** the retrieved records (grounded RAG) | LLM |
| 2.4 | **Result, translation, PDF** | Ranked list with CGHS cost (display only), sources, translation and a PDF export | Code |

### Design choice: rules vs LLM

| Step | Rules / code | LLM | Our choice |
|------|--------------|-----|------------|
| 1. Input to specialty | Fast and predictable, but misses new wording and can't read free text | Handles paraphrase and reports, but can hallucinate | **Hybrid.** The LLM extracts within the ICD-10 list and code validates |
| 2. Specialty to hospitals | Transparent and repeatable, but needs expert weights | Flexible but opaque, and may invent hospitals | **Code ranks (AHP-TOPSIS).** The LLM only explains |

### Research basis

| Source | Finding | Used for |
|--------|---------|----------|
| Bookimed, Medmonks | Human coordinators match hospitals per request | Human-coordinator baseline |
| Şahin & Cezlan, 2022 | AHP weights from 7 experts, then TOPSIS. Staff, care quality and equipment rank highest | AHP criteria template (Step 2) |
| Rules vs AI triage, 2024 | Both above 70% accuracy, with equal safety | Baselines in both steps |
| Grounded RAG triage | Accuracy 0.802 vs 0.542 for a plain LLM | Grounding the LLM in retrieved records |
| Rule-system review | Heavy manual programming, weak on nuanced language | Why Step 1 uses an LLM |

*Figures come from the papers' abstracts. Verify them against the full sources before citing.*

### How the code maps to the architecture

| Architecture stage | Module(s) in `src/mediroute/` |
|--------------------|-------------------------------|
| Patient input + reports | `backend/main.py` (`/api/analyze`, `/api/reports/parse`), `backend/services/pdf_parser.py` |
| 1.1 Extract condition | `backend/services/medical_context_extractor.py`, `patient_context_aggregator.py` |
| 1.2 Map to ICD-10 | `backend/services/icd10_mapper.py`, `specialty_routing.py` (rules, then embeddings, then zero-shot, then Ollama LLM) |
| 1.3 Validate | `backend/services/patient_context_validator.py` |
| 1.4 Specialty | `backend/services/specialty_filter.py`, `data/medical_taxonomy/` |
| 2.1 Filter + retrieve | `backend/services/faiss_retriever.py`, `filtered_faiss_retriever.py`, `keyword_retriever.py`, `semantic_query_builder.py` |
| 2.2 Rank | `backend/services/hospital_reranker.py`, `hospital_recommendation_engine.py` (AHP-TOPSIS is planned) |
| Orchestration | `backend/workflow/routing_state.py` (LangGraph state) |
| Hospital data (NABH, JCI) | `data_generator/` (scrapers, master-dataset and FAISS index builders) |

See [docs/PROJECT_TRACKER.md](docs/PROJECT_TRACKER.md) for what is done and what is pending.

---

## 3. Project structure

```
MediRoute/
├── src/mediroute/                 # Python package (src layout)
│   ├── backend/                   # FastAPI application
│   │   ├── main.py                # API routes and app entry point
│   │   ├── models.py, recommendation_models.py, medical_context.py   # Pydantic schemas
│   │   ├── services/              # Extraction, ICD-10, specialty routing, retrieval, ranking
│   │   ├── ingestion/             # Runtime hospital loader
│   │   └── workflow/              # LangGraph routing state
│   ├── data_generator/            # Offline pipelines that build the files in data/
│   │   ├── jci_scraper.py, nabh_finder_scraper.py        # Accreditation scrapers (Playwright)
│   │   ├── build_hospital_master.py                      # Merge candidates, JCI and NABH into a master sheet
│   │   ├── create_master_dataset.py, create_verification_sheet.py,
│   │   │   merge_verified_hospitals.py, check_verification_progress.py
│   │   ├── build_specialty_vocabulary.py, validate_specialty_normalization.py
│   │   └── build_hospital_embedding_dataset.py, build_faiss_index.py   # Vector store
│   └── utils/
│       └── paths.py               # Single source of truth for all project paths
├── frontend/                      # Static HTML/CSS/JS UI (patient, results, hospital pages)
├── tests/                         # pytest test suite
├── data/
│   ├── raw/                       # Source datasets and scraper inputs
│   ├── interim/                   # Scraper outputs (JCI, NABH, per-city masters)
│   ├── processed/                 # hospitals_master.csv, verification sheets
│   ├── medical_taxonomy/          # ICD-10 to specialty mapping, specialty vocabulary
│   └── vector_store/              # FAISS index and hospital metadata
├── scripts/                       # restart_app.ps1, smoke and verification scripts
├── docs/                          # Architecture diagram, project tracker, API playground, references
├── pyproject.toml                 # Package metadata and dependencies
├── setup.py                       # Shim for legacy tooling
├── requirements.txt               # Runtime dependencies
└── requirements-dev.txt           # Plus scraping, test and lint tools
```

## 4. Setup

Requirements: **Python 3.10+** (developed on 3.14), Windows/macOS/Linux. Optionally,
[Ollama](https://ollama.com) with `llama3.2` for the LLM specialty-routing fallback.

```powershell
git clone https://github.com/shubhamgithhub/MediRoute.git
cd MediRoute

python -m venv .venv
.\.venv\Scripts\Activate.ps1          # macOS/Linux: source .venv/bin/activate

pip install -e ".[dev,scraping]"      # Editable install of the package plus dev tools
# or: pip install -r requirements-dev.txt; pip install -e . --no-deps

playwright install chromium           # Only needed for the scrapers
```

Optional environment variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `MEDIROUTE_DATA_DIR` | `./data` | Use a data folder in another location |
| `MEDIROUTE_LOG_DIR` | `./logs` | Where `mediroute.log` is written |
| `MEDIROUTE_HOST` / `MEDIROUTE_PORT` | `127.0.0.1` / `8000` | Used by the `mediroute-api` command |
| `OLLAMA_API_BASE_URL` | `http://localhost:11434` | LLM fallback for specialty routing |

## 5. How to run

**Backend API**

```powershell
mediroute-api
# or
python -m uvicorn mediroute.backend.main:app --reload --host 127.0.0.1 --port 8000
# or, on Windows: also restarts Ollama and writes logs
.\scripts\restart_app.ps1
```

- Interactive API docs: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/api/health
- The first start takes about 1–2 minutes because the embedding models load.

**Frontend**

The frontend is static and calls the API at `http://127.0.0.1:8000`.

```powershell
python -m http.server 5500 --directory frontend
# open http://127.0.0.1:5500/index.html
```

**Main endpoints**

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/analyze` | Free-text query to specialty (Step 1) |
| POST | `/api/reports/parse` | Upload PDF reports and extract text |
| POST | `/api/medical-context` | Build a structured medical context |
| POST | `/api/hospitals/recommend` | Medical context to ranked hospitals (Step 2) |
| POST | `/api/hospitals/semantic-recommendations` | FAISS semantic hospital search |
| GET | `/api/hospitals/search`, `/api/hospitals/keyword-search` | Location and keyword search |
| GET | `/api/icd10/map`, `/api/icd10/code/{code}` | ICD-10 lookups |

There are more request examples in [docs/API_TEST_PLAYGROUND.md](docs/API_TEST_PLAYGROUND.md).

**Data pipelines** (run from the repo root)

```powershell
# Accreditation scraping, then a hospital master sheet
python -m mediroute.data_generator.jci_scraper --help
python -m mediroute.data_generator.nabh_finder_scraper --cities Chennai
python -m mediroute.data_generator.build_hospital_master `
    --candidates data/raw/data_generator/candidates/chennai.csv `
    --jci data/interim/jci/jci_chennai.csv --out data/interim/master/chennai_master.xlsx

# Taxonomy and vector store (rebuild after the hospital dataset changes)
python -m mediroute.data_generator.build_specialty_vocabulary
python -m mediroute.data_generator.validate_specialty_normalization
python -m mediroute.data_generator.build_hospital_embedding_dataset
python -m mediroute.data_generator.build_faiss_index
```

## 6. How to test

```powershell
pytest                       # Whole suite (tests/)
pytest tests/test_icd10_mapping.py -v
python -m tests.test_retrieval_pipeline     # Each test file also runs as a script with a printed report
```

- `tests/` covers ICD-10 mapping, medical context extraction, context validation, specialty
  inference, the semantic query builder, keyword and FAISS retrieval, and the end-to-end
  recommendation pipeline.
- Test cases are kept as data in `data/medical_taxonomy/*_test_cases.csv`.
- To run end-to-end API smoke checks, start a server and then run
  `python scripts/smoke_test_api.py`, or run `python scripts/verify_specialty_route.py`, which
  starts and stops its own server.

## 7. Project tracker

The milestones, status of each architecture stage, and next steps are in
**[docs/PROJECT_TRACKER.md](docs/PROJECT_TRACKER.md)**.

## 8. Disclaimer

MediRoute is an academic decision-support prototype. It is **not** a medical device and does not
give medical advice. Recommendations must be reviewed by a qualified clinician.
