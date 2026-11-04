"""Step 1 API: patient query / reports -> medical context and specialty."""

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile

from mediroute.common.medical_context import MedicalContext
from mediroute.specialty_routing.extraction.medical_context_extractor import (
    MedicalContextExtractor,
)
from mediroute.specialty_routing.extraction.patient_context_aggregator import (
    PatientContextAggregator,
)
from mediroute.specialty_routing.extraction.patient_context_validator import (
    PatientContextValidator,
)
from mediroute.specialty_routing.extraction.pdf_parser import PDFParser
from mediroute.specialty_routing.icd10_mapper import ICD10Mapper
from mediroute.specialty_routing.router import infer_medical_context_from_query
from mediroute.specialty_routing.schemas import PatientRequest
from mediroute.utils.logging_config import get_logger

logger = get_logger()

router = APIRouter(tags=["Step 1 - Specialty routing"])

icd10_mapper = ICD10Mapper()
pdf_parser = PDFParser()
medical_context_extractor = MedicalContextExtractor()
patient_context_aggregator = PatientContextAggregator()
patient_context_validator = PatientContextValidator()


@router.get("/api/icd10/map")
def map_medical_condition(condition: str):
    return icd10_mapper.find_by_condition(condition)


@router.get("/api/icd10/code/{icd10_code}")
def map_icd10_code(icd10_code: str):
    return icd10_mapper.find_by_icd10_code(icd10_code)


def infer_medical_context(query: str | PatientRequest):
    request_text = query
    if isinstance(query, PatientRequest):
        request_text = query.requirement or query.additionalPreference or ""
    if not isinstance(request_text, str):
        request_text = str(request_text or "")
    logger.info("Inferencing medical context for request: %s", request_text)
    result = infer_medical_context_from_query(request_text)
    logger.info("Medical context result: %s", result)
    return result


@router.post("/api/analyze")
def analyze_patient(request: PatientRequest):
    logger.info("INPUT RECEIVED: requirement=%s, location=%s, language=%s, additionalPreference=%s", request.requirement, request.location, request.language, request.additionalPreference)
    logger.info("Querying local specialty routing with patient details: %s", request.model_dump())
    medical_context = infer_medical_context(request)
    logger.info("LLM / routing output handled: %s", medical_context)
    logger.info("OUTPUT HANDLING: preparing final API response for requirement=%s", request.requirement)
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
        "medicalContext": medical_context,
        "note": "Specialty inference uses a local open-source retrieval + classification pipeline for demo purposes.",
    }


async def _read_pdf_uploads(files: list[UploadFile]) -> list[tuple[str, bytes]]:
    if not files:
        raise HTTPException(status_code=400, detail="No PDF files uploaded")

    uploaded_files = []
    for file in files:
        filename = file.filename or "unknown.pdf"
        if not filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {filename}. Only PDF files are allowed.",
            )
        uploaded_files.append((filename, await file.read()))
    return uploaded_files


@router.post("/api/reports/parse")
async def parse_medical_reports(
    files: Annotated[
        list[UploadFile],
        File(description="One or more medical PDF reports"),
    ]
):
    uploaded_files = await _read_pdf_uploads(files)
    return pdf_parser.parse_multiple_pdfs(uploaded_files)


@router.post("/api/medical-context")
async def extract_medical_context(files: list[UploadFile] = File(...)):
    uploaded_files = await _read_pdf_uploads(files)

    # Parse all uploaded PDFs
    parse_result = pdf_parser.parse_multiple_pdfs(uploaded_files)

    document_contexts = []
    medical_context_objects = []

    # Extract medical context from each PDF separately
    for document in parse_result["documents"]:
        filename = document["filename"]
        status = document["status"]
        text = document.get("text", "")

        if status == "success":
            context = medical_context_extractor.extract(text)
        elif status == "needs_ocr":
            context = MedicalContext(
                extraction_status="failed",
                clarification_required=True,
                clarification_reason=f"{filename} requires OCR before medical extraction",
            )
        else:
            context = MedicalContext(
                extraction_status="failed",
                clarification_required=True,
                clarification_reason=f"{filename} could not be parsed",
            )

        medical_context_objects.append(context)
        document_contexts.append(
            {
                "filename": filename,
                "parse_status": status,
                "medical_context": context.model_dump(),
            }
        )

    # Aggregate all reports into one patient-level context
    patient_context = patient_context_aggregator.aggregate(medical_context_objects)
    consistency_result = patient_context_validator.validate(
        medical_context_objects, patient_context
    )

    return {
        "parse_summary": {
            "overall_status": parse_result.get("overall_status"),
            "total_files": parse_result.get("total_files"),
            "successful_files": parse_result.get("successful_files"),
            "needs_ocr_files": parse_result.get("needs_ocr_files"),
            "error_files": parse_result.get("error_files"),
        },
        "document_contexts": document_contexts,
        "patient_medical_context": patient_context.model_dump(),
        "consistency_validation": consistency_result,
    }
