from pathlib import Path

import pandas as pd


from mediroute.utils.paths import RAW_DATA_DIR as _DATA_DIR
_HOSPITALS_FILES = (
    _DATA_DIR / "MediRoute_Hospitals_150.xlsx",
    _DATA_DIR / "NewMediRoute_Hospital_Dataset_150.xlsx",
)
_LIST_FIELDS = (
    "verified_specialties",
    "verified_subspecialties",
    "verified_procedures",
    "verified_facilities",
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
    hospitals_file = next(
        (path for path in _HOSPITALS_FILES if path.is_file()),
        _HOSPITALS_FILES[0],
    )
    hospitals_df = pd.read_excel(
        hospitals_file,
        sheet_name="Hospitals_150",
    )
    hospitals_df = hospitals_df.astype(object).where(
        pd.notna(hospitals_df),
        "",
    )

    hospitals = hospitals_df.to_dict(orient="records")
    for hospital in hospitals:
        for field in _LIST_FIELDS:
            hospital[field] = _split_list(hospital.get(field, ""))

        hospital["name"] = hospital.get("hospital_name", "")
        hospital["key_specialties"] = hospital.get("verified_specialties", [])
        hospital["facilities"] = hospital.get("verified_facilities", [])
        hospital["international_patient_support"] = hospital.get(
            "international_patient_service",
            "",
        )

    return hospitals


def search_hospitals_by_location(
    location: str,
) -> list[dict[str, object]]:
    hospitals = load_hospitals()
    normalized_location = location.strip().casefold()

    if not normalized_location or normalized_location == "no preference":
        return hospitals

    return [
        hospital
        for hospital in hospitals
        if normalized_location in str(hospital.get("city", "")).casefold()
    ]
