"""Cities and search areas shared by the hospital data, Step 2 and the patient page.

Source: data/processed/cities.csv (city, state, city_tier, search_area, other_names). A search
area groups cities a patient treats as one place: "Delhi NCR" = New Delhi + Gurugram + Noida,
"Mumbai" = Mumbai + Navi Mumbai. other_names = what patients also write ("Bombay", "Delhi").
Change the CSV, not code, to add a city or a name.
"""

from __future__ import annotations

import csv
import re
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
    other_names: tuple[str, ...] = ()


@lru_cache(maxsize=4)
def load_cities(path: Path = CITIES_FILE) -> tuple[City, ...]:
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return tuple(City(r["city"].strip(), r["state"].strip(), r["city_tier"].strip(), r["search_area"].strip(),
                          tuple(n.strip() for n in (r.get("other_names") or "").split(";") if n.strip()))
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
    areas = {c.search_area.casefold() for c in cities
             if text == c.name.casefold() or text in (n.casefold() for n in c.other_names)}
    if not areas and any(c.search_area.casefold() == text for c in cities):
        areas = {text}
    if not areas:
        return {value.strip()}  # unknown city: exact match only, so the patient gets "no city match"
    return {c.name for c in cities if c.search_area.casefold() in areas}


def _named_in(text: str, name: str) -> bool:
    return re.search(rf"(?<![\w]){re.escape(name.casefold())}(?![\w])", text) is not None


def state_in_text(text: str | None) -> str | None:
    """The state the patient names in free text ("CABG in Uttar Pradesh" -> "Uttar Pradesh"),
    whole words, ignoring case; None when no state or two different states are named.
    Use location_in_text first: a named city is more precise than its state."""
    lowered = (text or "").casefold()
    found = {c.state for c in load_cities() if lowered.strip() and _named_in(lowered, c.state)}
    return found.pop() if len(found) == 1 else None


def location_in_text(text: str | None) -> str | None:
    """The search area the patient names in free text ("bypass surgery in Bombay" -> "Mumbai"),
    for when no location was chosen on the page. Matches city names, search areas and
    other_names as whole words, ignoring case. None when no place, or two different search
    areas, are named: MediRoute does not guess between them."""
    lowered = (text or "").casefold()
    if not lowered.strip():
        return None
    found: set[str] = set()
    for c in load_cities():
        for name in (c.name, c.search_area, *c.other_names):
            if _named_in(lowered, name):
                found.add(c.search_area)
    return found.pop() if len(found) == 1 else None


def search_area_options(cities_with_hospitals: set[str]) -> list[dict]:
    """Choices for the patient page: one per search area that has hospitals, with its cities."""
    by_area: dict[str, list[str]] = {}
    for c in load_cities():
        if c.name in cities_with_hospitals:
            by_area.setdefault(c.search_area, []).append(c.name)
    return [{"value": area, "label": area if area_cities == [area] else f"{area} ({', '.join(area_cities)})",
             "cities": area_cities} for area, area_cities in sorted(by_area.items())]
