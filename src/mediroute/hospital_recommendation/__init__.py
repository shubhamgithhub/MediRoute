"""Step 2: specialty + patient context -> filtered, ranked hospital recommendations.

Layout:
    api.py              FastAPI routes (/api/hospitals/*)
    engine.py           HospitalRecommendationEngine: filter -> retrieve -> rerank
    specialty_filter.py Specialty normalisation and eligibility filtering
    hospital_loader.py  Load hospital dataset, location search
    schemas.py          Request models (HospitalRecommendationRequest)
    retrieval/          FAISS semantic, filtered FAISS and TF-IDF keyword retrieval
    ranking/            Reranking (AHP-TOPSIS planned)
"""
