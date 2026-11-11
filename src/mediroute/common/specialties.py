"""One canonical specialty list shared by Step 1 and Step 2.

Source: data/medical_taxonomy/specialties.csv. Change the CSV, not code, to add or rename a
specialty. Hospital labels reach these names through specialty_normalization.csv.
`in_hospital_data` is not typed by hand: it is true when at least one hospital in
data/processed/hospitals.csv lists the speciality, so Step 1 and Step 2 can't disagree.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from mediroute.utils.paths import HOSPITALS_FILE, TAXONOMY_DIR

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
            in_hospital_data=row["specialty"].strip() in hospital_specialty_counts(),
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


@lru_cache(maxsize=1)
def hospital_specialty_counts(path: Path = HOSPITALS_FILE) -> dict[str, int]:
    """Hospitals per speciality in the hospital table (website-verified or listed by the team)."""
    counts: dict[str, int] = {}
    if not Path(path).exists():
        return counts
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            names = {s.strip() for col in ("verified_specialties", "team_claimed_specialties")
                     for s in (row.get(col) or "").split(";") if s.strip() and s.strip() != "NA"}
            for name in names:
                counts[name] = counts.get(name, 0) + 1
    return counts


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
