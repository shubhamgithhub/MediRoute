"""Step 1 API: patient query / reports -> medical context and specialty."""

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile

from mediroute.specialty_routing.extraction.pdf_parser import PDFParser
from mediroute.specialty_routing.service import get_service
from mediroute.specialty_routing.schemas import PatientRequest
from mediroute.utils.logging_config import get_logger

logger = get_logger()

router = APIRouter(tags=["Step 1 - Specialty routing"])

pdf_parser = PDFParser()
# The old /api/icd10/* and /api/medical-context routes (keyword ICD mapper, 11 Nov 2026) were moved to
# archive/code/specialty_routing/: the Step 1 vote pipeline behind /api/analyze replaced them.


def infer_medical_context(query: str | PatientRequest):
    request_text = query
    if isinstance(query, PatientRequest):
        request_text = query.requirement or query.additionalPreference or ""
    if not isinstance(request_text, str):
        request_text = str(request_text or "")
    return get_service().analyze(request_text)


@router.post("/api/analyze")
def analyze_patient(request: PatientRequest):
    # The Step 1 pipeline logs every stage with a request_id (logs/step1_trace.jsonl).
    logger.info("analyze request: location=%s language=%s report_chars=%d round=%d selected=%s parent=%s",
                request.location, request.language, len(request.reportText or ""), request.clarificationRound,
                request.selectedSpecialty, request.parentRequestId)
    medical_context = get_service().analyze_request(request)
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
        "note": ("Step 1 suggests a speciality to search using three independent methods (keyword search, "
                 "meaning search, local LLM) and a majority vote. Discovery support only, not a diagnosis."),
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
