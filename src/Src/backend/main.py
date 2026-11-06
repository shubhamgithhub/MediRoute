from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from ..Ingestion.load_hospitals import load_hospitals, search_hospitals_by_location
from .models import PatientRequest
from src.Src.backend.services.icd10_mapper import ICD10Mapper
from typing import Annotated
from fastapi import File, Form, UploadFile, HTTPException
from src.Src.backend.services.pdf_parser import PDFParser
from src.Src.backend.services.medical_context_extractor import (
    MedicalContextExtractor,
)

from src.Src.backend.services.patient_context_aggregator import (
    PatientContextAggregator,
)
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

import logging
from pathlib import Path

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from src.Src.backend.workflow.patient_routing_graph import (
    PatientRoutingGraph,
)

# Step 12 — Load the patient-routing graph once.
patient_routing_graph = PatientRoutingGraph()

routing_logger = logging.getLogger(__name__)


MAX_REPORTS = 5
MAX_PDF_BYTES = 10 * 1024 * 1024  # 10 MB per report
MAX_TOTAL_BYTES = 30 * 1024 * 1024

keyword_retriever = KeywordHospitalRetriever()
semantic_query_builder = SemanticQueryBuilder()

faiss_retriever = FaissHospitalRetriever()
recommendation_engine = HospitalRecommendationEngine(faiss_retriever=faiss_retriever)
patient_context_validator = PatientContextValidator()
patient_context_aggregator = PatientContextAggregator()

medical_context_extractor = MedicalContextExtractor()
app = FastAPI(
    title="MediRoute API",
    description="Backend API for the MediRoute hospital routing application",
    version="1.0.0",
)


def custom_openapi():
    """Make multipart PDF fields display as file pickers in Swagger UI.

    FastAPI/Pydantic versions may emit contentEncoding/contentMediaType
    instead of OpenAPI's format=binary, including inside nullable anyOf.
    Only multipart fields named `files` are changed.
    """
    if app.openapi_schema is not None:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    components = schema.get("components", {}).get("schemas", {})

    def mark_file_schema(prop):
        # Nullable upload fields can be anyOf: [array, null].
        for union_name in ("anyOf", "oneOf"):
            if union_name in prop:
                for variant in prop[union_name]:
                    if isinstance(variant, dict):
                        mark_file_schema(variant)
                return

        if prop.get("type") == "array":
            items = prop.setdefault("items", {})
            if isinstance(items, dict):
                items["type"] = "string"
                items["format"] = "binary"
                items.pop("contentEncoding", None)
                items.pop("contentMediaType", None)
        elif prop.get("type") == "string":
            prop["format"] = "binary"
            prop.pop("contentEncoding", None)
            prop.pop("contentMediaType", None)

    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            multipart = (
                operation.get("requestBody", {})
                .get("content", {})
                .get("multipart/form-data")
            )
            if not multipart:
                continue
            body = multipart.get("schema", {})
            ref = body.get("$ref")
            target = components.get(ref.rsplit("/", 1)[-1], {}) if ref else body
            file_prop = target.get("properties", {}).get("files")
            if isinstance(file_prop, dict):
                mark_file_schema(file_prop)

    app.openapi_schema = schema
    return schema


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
        list[UploadFile], File(description="One or more medical PDF reports")
    ],
):

    if not files:
        raise HTTPException(status_code=400, detail="No PDF files uploaded")

    uploaded_files = []

    for file in files:

        filename = file.filename or "unknown.pdf"

        if not filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unsupported file type: {filename}. "
                    f"Only PDF files are allowed."
                ),
            )

        file_bytes = await file.read()

        uploaded_files.append((filename, file_bytes))

    result = pdf_parser.parse_multiple_pdfs(uploaded_files)

    return result


@app.post("/api/medical-context")
async def extract_medical_context(files: list[UploadFile] = File(...)):

    if not files:
        raise HTTPException(status_code=400, detail="No PDF files uploaded")

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
                ),
            )

        file_bytes = await file.read()

        uploaded_files.append((filename, file_bytes))

    # -----------------------------------------
    # STEP 8
    # Parse all uploaded PDFs
    # -----------------------------------------

    parse_result = pdf_parser.parse_multiple_pdfs(uploaded_files)

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

            context = medical_context_extractor.extract(text)

        # Scanned PDF requiring OCR
        elif status == "needs_ocr":

            context = MedicalContext(
                extraction_status="failed",
                clarification_required=True,
                clarification_reason=(
                    f"{filename} requires OCR " f"before medical extraction"
                ),
            )

        # Broken / unreadable file
        else:

            context = MedicalContext(
                extraction_status="failed",
                clarification_required=True,
                clarification_reason=(f"{filename} could not be parsed"),
            )

        medical_context_objects.append(context)

        document_contexts.append(
            {
                "filename": filename,
                "parse_status": status,
                "medical_context": (context.model_dump()),
            }
        )

    # -----------------------------------------
    # Aggregate all reports into one
    # patient-level context
    # -----------------------------------------

    patient_context = patient_context_aggregator.aggregate(medical_context_objects)
    consistency_result = patient_context_validator.validate(
        medical_context_objects, patient_context
    )

    # -----------------------------------------
    # Return both document-level and
    # patient-level results
    # -----------------------------------------

    return {
        "parse_summary": {
            "overall_status": parse_result.get("overall_status"),
            "total_files": parse_result.get("total_files"),
            "successful_files": parse_result.get("successful_files"),
            "needs_ocr_files": parse_result.get("needs_ocr_files"),
            "error_files": parse_result.get("error_files"),
        },
        "document_contexts": (document_contexts),
        "patient_medical_context": (patient_context.model_dump()),
        "consistency_validation": (consistency_result),
    }


@app.post("/api/hospitals/semantic-recommendations")
def semantic_hospital_recommendations(context: MedicalContext, top_k: int = 10):

    # ---------------------------------------------
    # Validate routing context
    # ---------------------------------------------

    if not context.primary_specialty:
        raise HTTPException(
            status_code=400,
            detail=("Medical context does not contain " "a primary specialty"),
        )

    # ---------------------------------------------
    # Build semantic query
    # ---------------------------------------------

    query = semantic_query_builder.build(context)

    if not query:
        raise HTTPException(
            status_code=400,
            detail=("Unable to build semantic query " "from medical context"),
        )

    # ---------------------------------------------
    # FAISS semantic retrieval
    # ---------------------------------------------

    results = faiss_retriever.search(query=query, top_k=top_k)

    return {
        "retrieval_method": "faiss_semantic",
        "semantic_query": query,
        "primary_specialty": context.primary_specialty,
        "top_k": top_k,
        "count": len(results),
        "results": results,
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
def keyword_hospital_search(query: str, top_k: int = 10):

    results = keyword_retriever.search(query=query, top_k=top_k)

    return {
        "retrieval_method": "tfidf_keyword",
        "query": query,
        "top_k": top_k,
        "count": len(results),
        "results": results,
    }

@app.post("/api/patient-routing")
async def run_patient_routing(
    files: list[UploadFile] | None = File(default=None),
    requirement: str = Form(default=""),
    preferred_city: str | None = Form(default=None),
    preferred_state: str | None = Form(default=None),
    top_k: int = Form(default=5, ge=1, le=20),
):
    """
    Step 12H:
    Run the complete MediRoute LangGraph workflow.

    Input:
      - One or more PDF medical reports
      - Patient requirement
      - Optional city/state preferences
      - Number of recommendations

    Output:
      - Medical context and validation summary
      - Hospital recommendations, or
      - Clarification request

    Raw PDF bytes are never included in the response.
    """

    uploaded_files = files or []

    if len(uploaded_files) > MAX_REPORTS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Maximum {MAX_REPORTS} PDF reports "
                "are allowed per request."
            ),
        )

    report_files = []
    total_bytes = 0

    for upload in uploaded_files:
        filename = Path(
            (upload.filename or "unnamed.pdf")
            .replace("\\", "/")
        ).name

        if not filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=400,
                detail="Only PDF files are supported.",
            )

        try:
            content = await upload.read(MAX_PDF_BYTES + 1)
        finally:
            await upload.close()

        if len(content) > MAX_PDF_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"PDF exceeds the "
                    f"{MAX_PDF_BYTES // (1024 * 1024)} "
                    "MB per-file limit."
                ),
            )

        total_bytes += len(content)

        if total_bytes > MAX_TOTAL_BYTES:
            raise HTTPException(
                status_code=413,
                detail="Total uploaded PDF size exceeds 30 MB.",
            )

        # Basic PDF signature check.
        # This does not replace production security scanning.
        if not content.startswith(b"%PDF-"):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid PDF file: {filename}",
            )

        report_files.append({
            "filename": filename,
            "content": content,
        })

    # Build the input state for the existing graph.
    initial_state = {
        "patient_request": {
            "requirement": requirement,
        },
        "report_files": report_files,
        "preferred_city": preferred_city,
        "preferred_state": preferred_state,
        "top_k": top_k,
        "workflow_status": "started",
        "current_step": "start",
        "routing_ready": False,
        "clarification_required": False,
        "clarification_reason": None,
        "error_message": None,
    }

    try:
        # The existing LangGraph invocation is synchronous
        # and may perform CPU-intensive model inference.
        # Run it outside the async event loop.
        result = await run_in_threadpool(
            patient_routing_graph.invoke,
            initial_state,
        )

    except Exception:
        routing_logger.exception(
            "MediRoute patient-routing execution failed"
        )

        return JSONResponse(
            status_code=500,
            content={
                "workflow_status": "failed",
                "message": (
                    "An internal routing error occurred."
                ),
            },
        )

    workflow_status = result.get(
        "workflow_status",
        "failed",
    )

    recommendation = (
        result.get("recommendation_result") or {}
    )

    # Return only selected fields.
    # Never return result["report_files"], which contains
    # sensitive uploaded PDF bytes.
    response = {
        "workflow_status": workflow_status,
        "current_step": result.get("current_step"),
        "routing_ready": result.get(
            "routing_ready",
            False,
        ),
        "parse_summary": {
    key: (result.get("parse_summary") or {}).get(key)
    for key in (
        "overall_status",
        "total_files",
        "successful_files",
        "needs_ocr_files",
        "error_files",
    )
},
        "patient_medical_context": result.get(
            "patient_medical_context"
        ),
        "consistency_validation": result.get(
            "consistency_validation"
        ),
        "clarification_required": result.get(
            "clarification_required",
            False,
        ),
        "clarification_type": result.get(
            "clarification_type"
        ),
        "clarification_reason": result.get(
            "clarification_reason"
        ),
        "recommendation_result": recommendation,
    }

    if workflow_status == "failed":
        # Internal diagnostic details remain server-side.
        routing_logger.error(
            "Patient routing ended in failed state"
        )

        return JSONResponse(
            status_code=500,
            content=jsonable_encoder({
                "workflow_status": "failed",
                "message": (
                    "MediRoute could not complete "
                    "the routing workflow."
                ),
            }),
        )

    return jsonable_encoder(response)
