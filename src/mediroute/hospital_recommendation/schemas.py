from typing import Optional

from pydantic import BaseModel, Field

from mediroute.common.medical_context import MedicalContext


class HospitalRecommendationRequest(BaseModel):
    context: MedicalContext
    preferred_city: Optional[str] = None
    preferred_state: Optional[str] = None
    top_k: int = Field(default=5, ge=1, le=20)
