from typing import Optional

from pydantic import BaseModel, Field


class PatientRequest(BaseModel):
    requirement: str
    location: str
    language: str
    additionalPreference: str

    reportName: list[str] = Field(
        default_factory=list
    )