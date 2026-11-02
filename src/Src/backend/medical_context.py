from pydantic import BaseModel, Field
from typing import Optional


class MedicalContext(BaseModel):
    diagnoses: list[str] = Field(default_factory=list)

    symptoms: list[str] = Field(default_factory=list)

    procedures: list[str] = Field(default_factory=list)

    medications: list[str] = Field(default_factory=list)

    clinical_findings: list[str] = Field(default_factory=list)

    icd10_codes: list[str] = Field(default_factory=list)

    canonical_specialties: list[str] = Field(default_factory=list)

    primary_specialty: Optional[str] = None

    extraction_status: str = "pending"

    clarification_required: bool = False

    clarification_reason: Optional[str] = None
    
if __name__ == "__main__":
    context = MedicalContext()

    print(context.model_dump())