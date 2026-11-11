"""Cities and search areas shared by the hospital data, Step 2 and the patient page.

Source: data/reference/cities.csv (city, state, city_tier, search_area). A search area groups
cities a patient treats as one place: "Delhi NCR" = New Delhi + Gurugram + Noida, "Mumbai" =
Mumbai + Navi Mumbai. Change the CSV, not code, to add a city.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from mediroute.utils.paths import CITIES_FILE

NO_PREFERENCE = {"", "no preference", "any", "anywhere", "other"}


@dataclass(frozen=True)
class City:
    name: str
    state: str
    tier: str
    search_area: str


@lru_cache(maxsize=4)
def load_cities(path: Path = CITIES_FILE) -> tuple[City, ...]:
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return tuple(City(r["city"].strip(), r["state"].strip(), r["city_tier"].strip(), r["search_area"].strip())
                     for r in csv.DictReader(handle))


def city_names() -> list[str]:
    return [c.name for c in load_cities()]


def resolve_location(value: str | None) -> set[str] | None:
    """Cities to search for what the patient chose: a city ("Gurugram"), a search area
    ("Delhi NCR"), or nothing. Returns None for no preference. Matching ignores case; a city
    returns its whole search area, so "New Delhi" also finds Gurugram hospitals."""
    text = (value or "").strip().casefold()
    if text in NO_PREFERENCE:
        return None
    cities = load_cities()
    areas = {c.search_area.casefold() for c in cities if c.name.casefold() == text}
    if not areas and any(c.search_area.casefold() == text for c in cities):
        areas = {text}
    if not areas:
        return {value.strip()}  # unknown city: exact match only, so the patient gets "no city match"
    return {c.name for c in cities if c.search_area.casefold() in areas}


def search_area_options(cities_with_hospitals: set[str]) -> list[dict]:
    """Choices for the patient page: one per search area that has hospitals, with its cities."""
    by_area: dict[str, list[str]] = {}
    for c in load_cities():
        if c.name in cities_with_hospitals:
            by_area.setdefault(c.search_area, []).append(c.name)
    return [{"value": area, "label": area if area_cities == [area] else f"{area} ({', '.join(area_cities)})",
             "cities": area_cities} for area, area_cities in sorted(by_area.items())]
