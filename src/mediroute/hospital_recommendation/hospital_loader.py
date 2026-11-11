from pathlib import Path

import pandas as pd


from mediroute.common.locations import resolve_location
from mediroute.utils.paths import HOSPITALS_FILE

# data/processed/hospitals.csv: the one hospital table (see build_hospitals_table.py)
_LIST_FIELDS = (
    "verified_specialties",
    "team_claimed_specialties",
    "subspecialties",
    "procedures",
    "facilities",
)


def _split_list(value: object) -> list[str]:
    if not value:
        return []

    return [
        item.strip()
        for item in str(value).replace("|", ";").replace(",", ";").split(";")
        if item.strip()
    ]


def load_hospitals() -> list[dict[str, object]]:
    hospitals_df = pd.read_csv(HOSPITALS_FILE, dtype=str, keep_default_na=False)
    hospitals_df = hospitals_df.astype(object).where(
        hospitals_df != "",
        "",
    )
    hospitals = hospitals_df.to_dict(orient="records")
    for hospital in hospitals:
        for field in _LIST_FIELDS:
            hospital[field] = _split_list(hospital.get(field, ""))

        hospital["name"] = hospital.get("hospital_name", "")
        hospital["key_specialties"] = hospital.get("verified_specialties", [])

        hospital["international_patient_support"] = hospital.get(
            "international_patient_service",
            "",
        )

    return hospitals


def search_hospitals_by_location(
    location: str,
) -> list[dict[str, object]]:
    hospitals = load_hospitals()
    cities = resolve_location(location)  # a city or a search area such as "Delhi NCR"
    if cities is None:
        return hospitals
    return [hospital for hospital in hospitals if hospital.get("city") in cities]
