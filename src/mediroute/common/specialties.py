"""The speciality master list and the rules that map anything to it, shared by Step 1 and Step 2.

Two hand-maintained files (both in data/processed/, both in the doctor review):

* specialties.csv: the master list. 26 specialities with a description and routing boundaries
  (route_here_when / not_here) that the LLM reads. Only these names can ever be suggested or
  searched; every other file refers to them.
* specialty_mapping.csv: every "X -> speciality" rule in one table, one row per rule:

    source       value                     specialty                 evidence_type
    ccsr         GEN005 (AHRQ category)    Urology                   diagnosis | symptom | status
    cghs_label   CGHS section label        Nephrology                procedure
    cghs_name    text in a procedure name  Organ Transplant          procedure
    lay_term     patient wording           Urology                   strong | weak
    hospital     hospital department name  Neurology;Neurosurgery    (Step 2)

  NONE = known value that is not routing evidence. Several specialities are joined with ";".

`in_hospital_data` is not typed by hand: it is true when at least one hospital in
data/processed/hospitals.csv lists the speciality, so Step 1 and Step 2 can't disagree.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from mediroute.utils.paths import HOSPITALS_FILE, SPECIALTIES_FILE, SPECIALTY_MAPPING_FILE

MAPPING_SOURCES = ("ccsr", "cghs_label", "cghs_name", "lay_term", "hospital")
EVIDENCE_TYPES = {"ccsr": {"diagnosis", "symptom", "status"}, "cghs_label": {"procedure"},
                  "cghs_name": {"procedure"}, "lay_term": {"strong", "weak"}, "hospital": {""}}
# matches of these kinds are weak routing evidence: they count half in the lookup voters
WEAK_EVIDENCE = {"symptom", "weak"}


@dataclass(frozen=True)
class Specialty:
    name: str
    care_category: str
    in_hospital_data: bool
    description: str
    route_here_when: str = ""
    not_here: str = ""


@dataclass(frozen=True)
class MappingRule:
    source: str
    value: str
    description: str
    specialties: tuple[str, ...]  # empty = NONE
    evidence_type: str
    reason: str
    review_status: str


def _read(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


@lru_cache(maxsize=4)
def load_specialties(path: Path = SPECIALTIES_FILE) -> tuple[Specialty, ...]:
    specialties = tuple(
        Specialty(
            name=row["specialty"].strip(),
            care_category=row["care_category"].strip(),
            in_hospital_data=row["specialty"].strip() in hospital_specialty_counts(),
            description=row["description"].strip(),
            route_here_when=(row.get("route_here_when") or "").strip(),
            not_here=(row.get("not_here") or "").strip(),
        )
        for row in _read(path)
        if row.get("specialty", "").strip()
    )
    names = [s.name.lower() for s in specialties]
    if len(names) != len(set(names)):
        raise ValueError(f"Duplicate specialty names in {path}")
    return specialties


@lru_cache(maxsize=4)
def load_mapping(path: Path = SPECIALTY_MAPPING_FILE) -> tuple[MappingRule, ...]:
    rules = []
    for row in _read(path):
        names = tuple(n.strip() for n in (row.get("specialty") or "").split(";") if n.strip() and n.strip() != "NONE")
        rules.append(MappingRule(source=row["source"].strip(), value=row["value"].strip(),
                                 description=(row.get("description") or "").strip(), specialties=names,
                                 evidence_type=(row.get("evidence_type") or "").strip(),
                                 reason=(row.get("reason") or "").strip(),
                                 review_status=(row.get("review_status") or "").strip()))
    return tuple(rules)


def mapping_rules(source: str) -> list[MappingRule]:
    return [r for r in load_mapping() if r.source == source]


def lay_terms(strength: str | None = None) -> list[MappingRule]:
    """Patient wording -> speciality; strength "strong" or "weak" filters, None returns both."""
    return [r for r in mapping_rules("lay_term") if r.specialties and (strength is None or r.evidence_type == strength)]


@lru_cache(maxsize=1)
def hospital_label_map() -> dict[str, set[str]]:
    """Hospital department name (casefolded) -> specialities; NONE labels map to an empty set.
    Canonical names also match themselves."""
    mapping: dict[str, set[str]] = {}
    for rule in mapping_rules("hospital"):
        mapping.setdefault(rule.value.casefold(), set()).update(rule.specialties)
    for name in specialty_names():
        mapping.setdefault(name.casefold(), set()).add(name)
    return mapping


def validate_mapping() -> list[str]:
    """Problems in specialty_mapping.csv (empty list = valid). Used by tests and the rebuild."""
    problems, seen = [], set()
    valid = set(specialty_names())
    for rule in load_mapping():
        key = (rule.source, rule.value.casefold())
        if rule.source not in MAPPING_SOURCES:
            problems.append(f"unknown source '{rule.source}' ({rule.value})")
        if key in seen:
            problems.append(f"duplicate rule {key}")
        seen.add(key)
        unknown = set(rule.specialties) - valid
        if unknown:
            problems.append(f"{rule.source} '{rule.value}': not in specialties.csv: {sorted(unknown)}")
        allowed = EVIDENCE_TYPES.get(rule.source, set())
        if rule.specialties and rule.evidence_type not in allowed:
            problems.append(f"{rule.source} '{rule.value}': evidence_type '{rule.evidence_type}' not in {sorted(allowed)}")
    return problems


@lru_cache(maxsize=1)
def hospital_specialty_counts(path: Path = HOSPITALS_FILE) -> dict[str, int]:
    """Hospitals per speciality in the hospital table (website-verified or listed by the team)."""
    counts: dict[str, int] = {}
    if not Path(path).exists():
        return counts
    for row in _read(path):
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
