from typing import Optional

from pydantic import BaseModel


class PatientRequest(BaseModel):
    requirement: str
    location: str
    language: str
    additionalPreference: Optional[str] = None
    reportName: Optional[str] = None
