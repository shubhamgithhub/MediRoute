from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..Ingestion.load_hospitals import load_hospitals, search_hospitals_by_location
from .models import PatientRequest
from src.Src.backend.services.icd10_mapper import ICD10Mapper

from typing import Annotated
from fastapi import File, UploadFile, HTTPException
from src.Src.backend.services.pdf_parser import PDFParser


app = FastAPI(
    title="MediRoute API",
    description="Backedn API for the MediRoute hospital routing application",
    version="1.0.0",
)
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
        File(description="One or more medical PDF reports")
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