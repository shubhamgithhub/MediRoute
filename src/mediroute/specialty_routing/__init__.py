"""Step 1: patient query and reports -> suggested speciality to search.

Layout:
    api.py          FastAPI routes (/api/analyze, /api/reports/parse)
    service.py      Entry point used by the API and the workflow (runs step1/pipeline.py)
    step1/          The vote pipeline: protect, emergency rules, evidence, V1/V2/V3 votes, decision
    routes.py       LLM route (V3) and a keyword-rules baseline
    schemas.py      Request models (PatientRequest)
    extraction/     PDF report parsing
"""
