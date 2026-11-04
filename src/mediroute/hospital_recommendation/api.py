"""Step 2 API: specialty / medical context -> hospital search and recommendations."""

from fastapi import APIRouter, HTTPException

from mediroute.common.medical_context import MedicalContext
from mediroute.hospital_recommendation.engine import HospitalRecommendationEngine
from mediroute.hospital_recommendation.hospital_loader import (
    load_hospitals,
    search_hospitals_by_location,
)
from mediroute.hospital_recommendation.retrieval.faiss_retriever import (
    FaissHospitalRetriever,
)
from mediroute.hospital_recommendation.retrieval.keyword_retriever import (
    KeywordHospitalRetriever,
)
from mediroute.hospital_recommendation.retrieval.semantic_query_builder import (
    SemanticQueryBuilder,
)
from mediroute.hospital_recommendation.schemas import HospitalRecommendationRequest

router = APIRouter(tags=["Step 2 - Hospital recommendation"])

keyword_retriever = KeywordHospitalRetriever()
semantic_query_builder = SemanticQueryBuilder()
faiss_retriever = FaissHospitalRetriever()
recommendation_engine = HospitalRecommendationEngine(faiss_retriever=faiss_retriever)


@router.get("/api/hospitals")
def get_hospitals():
    hospitals = load_hospitals()
    return {
        "status": "success",
        "count": len(hospitals),
        "hospitals": hospitals,
    }


@router.get("/api/hospitals/search")
def search_hospitals(location: str = "No preference"):
    hospitals = search_hospitals_by_location(location)
    return {
        "status": "success",
        "location": location,
        "count": len(hospitals),
        "hospitals": hospitals,
    }


@router.post("/api/hospitals/semantic-recommendations")
def semantic_hospital_recommendations(context: MedicalContext, top_k: int = 10):
    # Validate routing context
    if not context.primary_specialty:
        raise HTTPException(
            status_code=400,
            detail="Medical context does not contain a primary specialty",
        )

    # Build semantic query
    query = semantic_query_builder.build(context)
    if not query:
        raise HTTPException(
            status_code=400,
            detail="Unable to build semantic query from medical context",
        )

    # FAISS semantic retrieval
    results = faiss_retriever.search(query=query, top_k=top_k)

    return {
        "retrieval_method": "faiss_semantic",
        "semantic_query": query,
        "primary_specialty": context.primary_specialty,
        "top_k": top_k,
        "count": len(results),
        "results": results,
    }


@router.post("/api/hospitals/recommend")
def recommend_hospitals(request: HospitalRecommendationRequest):
    return recommendation_engine.recommend(
        context=request.context,
        preferred_city=request.preferred_city,
        preferred_state=request.preferred_state,
        top_k=request.top_k,
    )


@router.get("/api/hospitals/keyword-search")
def keyword_hospital_search(query: str, top_k: int = 10):
    results = keyword_retriever.search(query=query, top_k=top_k)
    return {
        "retrieval_method": "tfidf_keyword",
        "query": query,
        "top_k": top_k,
        "count": len(results),
        "results": results,
    }
