from typing import Any

from pydantic import BaseModel, Field, field_validator


class ClarificationAnswers(BaseModel):
    """Answers to the Step 1 clarification form (all optional)."""

    body_area: str = ""
    existing_diagnosis: str = ""
    recommended_procedure: str = ""


class PatientRequest(BaseModel):
    requirement: str = Field("", description="What the patient types: problem, diagnosis or procedure")
    location: str = Field("No preference", description="Preferred city (used by Step 2)")
    language: str = Field("English", description="Preferred language (display only for now)")
    additionalPreference: str = ""
    reportName: list[str] | str | None = Field(default_factory=list)

    # Step 1 voting pipeline (all optional, so existing clients keep working)
    reportText: str = Field("", description="Text extracted from uploaded reports (from /api/reports/parse)")
    clarification: ClarificationAnswers | None = Field(None, description="Answers to the clarification form")
    clarificationRound: int = Field(0, ge=0, le=5, description="How many clarification forms were already answered")
    selectedSpecialty: str | None = Field(None, description="Speciality the user picked from the list after clarification")
    parentRequestId: str | None = Field(None, description="request_id of the first request of this search, to link rounds in the logs")
    debug: bool = Field(False, description="Include votes and trace stage names in the response")

    @field_validator("reportName", mode="before")
    @classmethod
    def normalize_report_name(cls, value: Any) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()]
