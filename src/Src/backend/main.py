from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from ..Ingestion.load_hospitals import load_hospitals, search_hospitals_by_location
from .models import PatientRequest
from src.Src.backend.services.icd10_mapper import ICD10Mapper
from src.Src.backend.medical_context import MedicalContext
from typing import Annotated
from fastapi import File, UploadFile, HTTPException
from src.Src.backend.services.pdf_parser import PDFParser
from src.Src.backend.services.medical_context_extractor import (
    MedicalContextExtractor,
)

from src.Src.backend.services.patient_context_aggregator import ( PatientContextAggregator,)
from src.Src.backend.services.patient_context_validator import (
    PatientContextValidator,
)
from src.Src.backend.medical_context import MedicalContext
from src.Src.backend.services.semantic_query_builder import (
    SemanticQueryBuilder,
)
from src.Src.backend.services.faiss_retriever import (
    FaissHospitalRetriever,
)
from src.Src.backend.services.keyword_retriever import (
    KeywordHospitalRetriever,
)
from src.Src.backend.recommendation_models import HospitalRecommendationRequest
from src.Src.backend.services.hospital_recommendation_engine import (
    HospitalRecommendationEngine,
)

keyword_retriever = KeywordHospitalRetriever()
semantic_query_builder = SemanticQueryBuilder()

faiss_retriever = FaissHospitalRetriever()
recommendation_engine = HospitalRecommendationEngine(
    faiss_retriever=faiss_retriever
)
patient_context_validator = PatientContextValidator()
patient_context_aggregator = PatientContextAggregator()

medical_context_extractor = MedicalContextExtractor()
app = FastAPI(
    title="MediRoute API",
    description="Backedn API for the MediRoute hospital routing application",
    version="1.0.0",
)

def custom_openapi():

    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    schemas = (
        openapi_schema
        .get("components", {})
        .get("schemas", {})
    )

    for schema in schemas.values():

        properties = schema.get("properties", {})

        for prop in properties.values():

            # Single file
            if (
                prop.get("contentMediaType")
                == "application/octet-stream"
            ):
                prop.pop(
                    "contentMediaType",
                    None
                )

                prop["format"] = "binary"

            # Multiple files
            items = prop.get("items", {})

            if (
                items.get("contentMediaType")
                == "application/octet-stream"
            ):
                items.pop(
                    "contentMediaType",
                    None
                )

                items["format"] = "binary"

    app.openapi_schema = openapi_schema

    return app.openapi_schema


app.openapi = custom_openapi

icd10_mapper = ICD10Mapper()
pdf_parser = PDFParser()

@app.get("/api/icd10/map")
def map_medical_condition(condition: str):
    return icd10_mapper.find_by_condition(condition)

@app.get("/api/icd10/code/{icd10_code}")
def map_icd10_code(icd10_code: str):
    return icd10_mapper.find_by_icd10_code(icd10_code)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"message": "Welcome to the MediRoute API!"}


@app.get("/api/health")
def health_check():
    return {"status": "healthy", "service": "MediRoute API"}


@app.post("/api/analyze")
def analyze_patient(request: PatientRequest):
    return {
        "status": "success",
        "message": "Patient request received successfully",
        "patient": {
            "requirement": request.requirement,
            "location": request.location,
            "language": request.language,
            "additionalPreference": request.additionalPreference,
            "reportName": request.reportName,
        },
        "medicalContext": {
            "relevantSpecialty": "Cardiology",
            "careCategory": "Cardiac Care",
        },
        "note": "This is a demo backend response. AI analysis has not been implemented yet.",
    }


@app.get("/api/hospitals")
def get_hospitals():
    hospitals = load_hospitals()
    return {
        "status": "success",
        "count": len(hospitals),
        "hospitals": hospitals,
    }


@app.get("/api/hospitals/search")
def search_hospitals(location: str = "No preference"):
    hospitals = search_hospitals_by_location(location)
    return {
        "status": "success",
        "location": location,
        "count": len(hospitals),
        "hospitals": hospitals,
    }
    
@app.post("/api/reports/parse")

async def parse_medical_reports(
    files: Annotated[
        list[UploadFile],
        File(
            description="One or more medical PDF reports"
        )
    ]
):

    if not files:
        raise HTTPException(
            status_code=400,
            detail="No PDF files uploaded"
        )

    uploaded_files = []

    for file in files:

        filename = file.filename or "unknown.pdf"

        if not filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unsupported file type: {filename}. "
                    f"Only PDF files are allowed."
                )
            )

        file_bytes = await file.read()

        uploaded_files.append(
            (
                filename,
                file_bytes
            )
        )

    result = pdf_parser.parse_multiple_pdfs(
        uploaded_files
    )

    return result

@app.post("/api/medical-context")
async def extract_medical_context(
    files: list[UploadFile] = File(...)
):

    if not files:
        raise HTTPException(
            status_code=400,
            detail="No PDF files uploaded"
        )

    uploaded_files = []

    # -----------------------------------------
    # Read uploaded PDF files
    # -----------------------------------------

    for file in files:

        filename = file.filename or "unknown.pdf"

        if not filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unsupported file type: {filename}. "
                    f"Only PDF files are allowed."
                )
            )

        file_bytes = await file.read()

        uploaded_files.append(
            (
                filename,
                file_bytes
            )
        )

    # -----------------------------------------
    # STEP 8
    # Parse all uploaded PDFs
    # -----------------------------------------

    parse_result = pdf_parser.parse_multiple_pdfs(
        uploaded_files
    )

    document_contexts = []
    medical_context_objects = []

    # -----------------------------------------
    # STEP 9
    # Extract medical context from each PDF
    # separately
    # -----------------------------------------

    for document in parse_result["documents"]:

        filename = document["filename"]
        status = document["status"]
        text = document.get("text", "")

        # Readable PDF
        if status == "success":

            context = (
                medical_context_extractor.extract(
                    text
                )
            )

        # Scanned PDF requiring OCR
        elif status == "needs_ocr":

            context = MedicalContext(
                extraction_status="failed",
                clarification_required=True,
                clarification_reason=(
                    f"{filename} requires OCR "
                    f"before medical extraction"
                )
            )

        # Broken / unreadable file
        else:

            context = MedicalContext(
                extraction_status="failed",
                clarification_required=True,
                clarification_reason=(
                    f"{filename} could not be parsed"
                )
            )

        medical_context_objects.append(
            context
        )

        document_contexts.append(
            {
                "filename": filename,
                "parse_status": status,
                "medical_context": (
                    context.model_dump()
                )
            }
        )

    # -----------------------------------------
    # Aggregate all reports into one
    # patient-level context
    # -----------------------------------------

    patient_context = (
        patient_context_aggregator.aggregate(
            medical_context_objects
        )
    )
    consistency_result = (
        patient_context_validator.validate(
            medical_context_objects,
            patient_context
        )
    )

    # -----------------------------------------
    # Return both document-level and
    # patient-level results
    # -----------------------------------------

    return {
        "parse_summary": {
            "overall_status": parse_result.get(
                "overall_status"
            ),
            "total_files": parse_result.get(
                "total_files"
            ),
            "successful_files": parse_result.get(
                "successful_files"
            ),
            "needs_ocr_files": parse_result.get(
                "needs_ocr_files"
            ),
            "error_files": parse_result.get(
                "error_files"
            )
        },

        "document_contexts": (
            document_contexts
        ),

        "patient_medical_context": (
            patient_context.model_dump()
        ),
        "consistency_validation": (consistency_result)
    }


@app.post("/api/hospitals/semantic-recommendations")
def semantic_hospital_recommendations(
    context: MedicalContext,
    top_k: int = 10
):

    # ---------------------------------------------
    # Validate routing context
    # ---------------------------------------------

    if not context.primary_specialty:
        raise HTTPException(
            status_code=400,
            detail=(
                "Medical context does not contain "
                "a primary specialty"
            )
        )

    # ---------------------------------------------
    # Build semantic query
    # ---------------------------------------------

    query = (
        semantic_query_builder.build(
            context
        )
    )

    if not query:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unable to build semantic query "
                "from medical context"
            )
        )

    # ---------------------------------------------
    # FAISS semantic retrieval
    # ---------------------------------------------

    results = faiss_retriever.search(
        query=query,
        top_k=top_k
    )

    return {
        "retrieval_method":
            "faiss_semantic",

        "semantic_query":
            query,

        "primary_specialty":
            context.primary_specialty,

        "top_k":
            top_k,

        "count":
            len(results),

        "results":
            results
    }


@app.post("/api/hospitals/recommend")
def recommend_hospitals(
    request: HospitalRecommendationRequest,
):
    return recommendation_engine.recommend(
        context=request.context,
        preferred_city=request.preferred_city,
        preferred_state=request.preferred_state,
        top_k=request.top_k,
    )
@app.get("/api/hospitals/keyword-search")
def keyword_hospital_search(
    query: str,
    top_k: int = 10
):

    results = (
        keyword_retriever.search(
            query=query,
            top_k=top_k
        )
    )

    return {
        "retrieval_method":
            "tfidf_keyword",

        "query":
            query,

        "top_k":
            top_k,

        "count":
            len(results),

        "results":
            results
    }