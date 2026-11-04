from typing import Any

from pydantic import BaseModel, Field, field_validator


class PatientRequest(BaseModel):
    requirement: str
    location: str
    language: str
    additionalPreference: str = ""
    reportName: list[str] | str | None = Field(default_factory=list)

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