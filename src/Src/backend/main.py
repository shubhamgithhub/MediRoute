from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..Ingestion.load_hospitals import load_hospitals, search_hospitals_by_location
from .models import PatientRequest


app = FastAPI(
    title="MediRoute API",
    description="Backedn API for the MediRoute hospital routing application",
    version="1.0.0",
)

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
