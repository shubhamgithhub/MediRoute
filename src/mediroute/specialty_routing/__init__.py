"""Step 1: patient query and reports -> condition, ICD-10 code and medical specialty.

Layout:
    api.py          FastAPI routes (/api/analyze, /api/medical-context, /api/reports/parse, /api/icd10/*)
    router.py       SpecialtyRAGRouter: rules -> embedding candidates -> Ollama LLM -> zero-shot
    icd10_mapper.py ICD-10 <-> condition <-> specialty lookup
    schemas.py      Request models (PatientRequest)
    extraction/     PDF parsing and medical-context extraction, aggregation and validation
"""
