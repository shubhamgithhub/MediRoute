# MediRoute – Project Tracker

Last updated: **2026-11-05**. Update this file in the same PR as the work it describes.

**Legend:** ✅ Done · 🟡 In progress / partial · ⬜ Not started · 🔴 Blocked

---

## Overall progress (against the target architecture)

| Area | Status | Notes |
|------|--------|-------|
| Project setup and structure | ✅ | `src/` layout, `pyproject.toml`, tests folder, README |
| Step 1: input to specialty | 🟡 | Rules, embeddings and LLM routing work. LLM ICD-10 selection and the clarify loop are still pending |
| Step 2: specialty to ranked hospitals | 🟡 | Filtering and hybrid retrieval work. AHP-TOPSIS, grounded explanations and CGHS costs are pending |
| Data (hospitals, taxonomy) | 🟡 | 150-hospital dataset is indexed. NABH/JCI scraping is under way (Chennai first) |
| Frontend | 🟡 | Patient, results and hospital pages exist. They need ranking, explanation and cost views |
| Evaluation | ⬜ | Baselines and metrics are not yet defined in code |

---

## Step 1: Patient input to specialty and treatment

| ID | Task | Status | Implementation / next action |
|----|------|--------|------------------------------|
| S1.0 | Patient query and PDF report intake | ✅ | `/api/analyze`, `/api/reports/parse`, `services/pdf_parser.py` (PyMuPDF) |
| S1.1 | Extract condition (symptoms, urgency, confidence) | 🟡 | `medical_context_extractor.py` and `patient_context_aggregator.py` are rule- and lookup-based. **Next:** LLM extraction into the `MedicalContext` schema |
| S1.2 | Map to ICD-10 (retrieve, then LLM picks) | 🟡 | `icd10_mapper.py` does CSV lookup. `specialty_routing.py` chains rules, embeddings, zero-shot and Ollama. **Next:** retrieve top-k ICD codes, then constrained LLM choice |
| S1.3 | Validate, else ask user | 🟡 | `patient_context_validator.py` flags low confidence (`requires_human_review`). **Next:** clarifying-question loop in API and UI |
| S1.4 | Specialty and treatment + CGHS procedure candidates | 🟡 | ICD-10 to specialty via `data/medical_taxonomy/`. **Next:** CGHS procedure list and mapping |
| S1.5 | LangGraph orchestration | 🟡 | `workflow/routing_state.py` defines the state. **Next:** build the graph nodes and edges |

## Step 2: Specialty to ranked hospitals

| ID | Task | Status | Implementation / next action |
|----|------|--------|------------------------------|
| S2.1 | Filter hospitals by specialty and location | ✅ | `specialty_filter.py`, `filtered_faiss_retriever.py`, `/api/hospitals/search` |
| S2.2 | Hybrid retrieval (FAISS + keyword) | ✅ | `faiss_retriever.py`, `keyword_retriever.py`, `semantic_query_builder.py`, index in `data/vector_store/` |
| S2.3 | AHP weights (expert criteria) | ⬜ | Define criteria (staff, equipment, accreditation, …) following Şahin & Cezlan 2022 and collect expert pairwise weights |
| S2.4 | TOPSIS ranking | ⬜ | Replace or augment the heuristic `hospital_reranker.py` with AHP-TOPSIS scoring |
| S2.5 | Grounded LLM explanation | ⬜ | Explain the ranking using only the retrieved records and cite record fields |
| S2.6 | CGHS cost (display only) | ⬜ | Source the CGHS rate list and join it to procedures |
| S2.7 | Result translation + PDF export | ⬜ | Support a language preference (already in the request) and a downloadable PDF |

## Data

| ID | Task | Status | Notes |
|----|------|--------|-------|
| D1 | 150-hospital curated dataset | ✅ | `data/raw/NewMediRoute_Hospital_Dataset_150.xlsx` |
| D2 | Specialty vocabulary and normalisation | ✅ | `data/medical_taxonomy/`, `build_specialty_vocabulary.py` |
| D3 | ICD-10 to specialty mapping + test cases | ✅ | `icd10_specialty_mapping.csv`, `*_test_cases.csv` |
| D4 | Embedding dataset + FAISS index | ✅ | `build_hospital_embedding_dataset.py`, `build_faiss_index.py` |
| D5 | JCI accreditation scraping | 🟡 | `jci_scraper.py`. Chennai and all-India output is in `data/interim/jci/` |
| D6 | NABH accreditation lookup | 🟡 | `nabh_finder_scraper.py`. Match output is in `data/interim/nabh_master_matches.csv` |
| D7 | Per-city hospital master build | 🟡 | `build_hospital_master.py`. Chennai is done. **Next:** remaining target cities |
| D8 | Manual verification workflow | 🟡 | `create_verification_sheet.py`, `merge_verified_hospitals.py`, `check_verification_progress.py` |

## Frontend

| ID | Task | Status | Notes |
|----|------|--------|-------|
| F1 | Patient input page (query + report upload) | ✅ | `frontend/patient.html` |
| F2 | Results page | 🟡 | `frontend/results.html`. **Next:** show TOPSIS scores, explanation and cost |
| F3 | Hospital detail page | 🟡 | `frontend/hospital.html` |
| F4 | Clarifying-question UI (S1.3) | ⬜ | |
| F5 | Configurable API base URL | ⬜ | The URL `http://127.0.0.1:8000` is currently hard-coded in `frontend/js/*.js` |

## Evaluation and quality

| ID | Task | Status | Notes |
|----|------|--------|-------|
| E1 | Unit and pipeline tests | 🟡 | `tests/`, run with `pytest`. 5 pass, 1 fails |
| E1a | **Bug:** `test_blurry_vision_maps_to_ophthalmology` fails | 🔴 | The rule step correctly gives Ophthalmology. When the Ollama call times out, the zero-shot fallback overrides it with "Liver Care". Fix the fallback precedence in `specialty_routing.infer()` |
| E2 | Step 1 accuracy vs rules baseline | ⬜ | Measure specialty and ICD-10 accuracy on a labelled query set |
| E3 | Step 2 ranking quality vs human-coordinator baseline | ⬜ | |
| E4 | Grounding / hallucination check on explanations | ⬜ | |
| E5 | CI (lint + tests on push) | ⬜ | GitHub Actions running `ruff` and `pytest` |

---

## Next up (suggested order)

1. **S2.3–S2.4**: AHP-TOPSIS ranking, the core of Step 2's transparency claim.
2. **S1.2**: Retrieve-then-LLM ICD-10 selection.
3. **S1.3 + F4**: Validate-or-ask loop.
4. **S2.5**: Grounded explanations.
5. **E2/E3**: Evaluation against baselines, for the capstone report.
6. **D7**: Extend the hospital master beyond Chennai.

## Change log

| Date | Change |
|------|--------|
| 2026-11-05 | Restructured repo into `src/mediroute/{backend,data_generator,utils}`, `tests/`, `scripts/`, `docs/` and `data/{raw,interim,processed}`. Added packaging, README and this tracker |
