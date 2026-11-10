"""One canonical specialty list shared by Step 1 and Step 2.

Source: data/medical_taxonomy/specialties.csv. Change the CSV, not code, to add or rename a
specialty. Names match `verified_specialties` in the hospital master where `in_hospital_data`
is true.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from mediroute.utils.paths import TAXONOMY_DIR

SPECIALTIES_FILE = TAXONOMY_DIR / "specialties.csv"


@dataclass(frozen=True)
class Specialty:
    name: str
    care_category: str
    in_hospital_data: bool
    description: str
    keywords: tuple[str, ...]


@lru_cache(maxsize=4)
def load_specialties(path: Path = SPECIALTIES_FILE) -> tuple[Specialty, ...]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    specialties = tuple(
        Specialty(
            name=row["specialty"].strip(),
            care_category=row["care_category"].strip(),
            in_hospital_data=row["in_hospital_data"].strip().lower() == "true",
            description=row["description"].strip(),
            keywords=tuple(k.strip().lower() for k in row["keywords"].split(";") if k.strip()),
        )
        for row in rows
        if row.get("specialty", "").strip()
    )
    names = [s.name.lower() for s in specialties]
    if len(names) != len(set(names)):
        raise ValueError(f"Duplicate specialty names in {path}")
    return specialties


def specialty_names() -> list[str]:
    return [s.name for s in load_specialties()]


def get_specialty(name: str) -> Specialty | None:
    """Exact, case-insensitive lookup of a canonical name."""
    key = (name or "").strip().lower()
    for specialty in load_specialties():
        if specialty.name.lower() == key:
            return specialty
    return None


def care_category(name: str) -> str:
    specialty = get_specialty(name)
    return specialty.care_category if specialty else "Primary Care"
