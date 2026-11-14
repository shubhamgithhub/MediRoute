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
    body_area    answer to "which part of  Orthopaedics              answer
                 the body?" (Step 1 form)

  NONE = known value that is not routing evidence. Several specialities are joined with ";".

`in_hospital_data` is not typed by hand: it is true when at least one hospital in
data/processed/hospitals.csv lists the speciality, so Step 1 and Step 2 can't disagree.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from mediroute.utils.paths import (BODY_AREA_NEIGHBOURS_FILE, BODY_AREA_TAGS_FILE, HOSPITALS_FILE,
                                   SPECIALTIES_FILE, SPECIALTY_FALLBACKS_FILE, SPECIALTY_MAPPING_FILE)

MAPPING_SOURCES = ("ccsr", "cghs_label", "cghs_name", "lay_term", "hospital", "body_area")
EVIDENCE_TYPES = {"ccsr": {"diagnosis", "symptom", "status"}, "cghs_label": {"procedure"},
                  "cghs_name": {"procedure"}, "lay_term": {"strong", "weak"}, "hospital": {""},
                  "body_area": {"answer"}}
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


def body_area_specialties(answer: str) -> set[str]:
    """Specialities that treat the body area the patient chose in the clarification form
    (empty for "Other / not sure" or an unknown answer)."""
    wanted = (answer or "").strip().casefold()
    for rule in mapping_rules("body_area"):
        if rule.value.casefold() == wanted:
            return set(rule.specialties)
    return set()


def body_area_options() -> list[str]:
    """The answers to "which part of the body?" in the order of specialty_mapping.csv."""
    return [r.value for r in mapping_rules("body_area")]


# --------------------------------------------------------------------------- multi-area check (Step 1)
# body_area_tags.csv: each symptom is tagged (by the evidence LLM, from this fixed list) with a fine
# tag such as "throat_mouth"; the tag belongs to one form area ("Ear, nose and throat"). General
# symptoms (fever, tiredness, aches) are not counted. body_area_neighbours.csv: pairs of tags that one
# common illness crosses (reflux, cold, migraine); their two areas count as one when the message has
# no other tag in those areas (so heartburn + sore throat is one area, heartburn + ear pain is two).
@dataclass(frozen=True)
class AreaTag:
    tag: str
    form_area: str
    counted: bool
    examples: str


@lru_cache(maxsize=2)
def load_area_tags(path: Path = BODY_AREA_TAGS_FILE) -> tuple[AreaTag, ...]:
    return tuple(AreaTag(row["tag"].strip(), row["form_area"].strip(), row["counted"].strip().lower() == "yes",
                         (row.get("examples") or "").strip())
                 for row in _read(path) if (row.get("tag") or "").strip())


@lru_cache(maxsize=2)
def load_area_neighbours(path: Path = BODY_AREA_NEIGHBOURS_FILE) -> tuple[tuple[frozenset, frozenset, str], ...]:
    def tags(cell: str) -> frozenset:
        return frozenset(t.strip() for t in (cell or "").split(";") if t.strip())
    return tuple((tags(row["tags_a"]), tags(row["tags_b"]), (row.get("counts_as_one_because") or "").strip())
                 for row in _read(path) if (row.get("tags_a") or "").strip())


# specialty_fallbacks.csv: for a speciality, related ones (in order) whose department often gives the
# same care. Step 2 shows hospitals in the patient's area with a related speciality only when no hospital
# there has the suggested one, as a separate, labelled group; the suggested speciality never changes.
@dataclass(frozen=True)
class SpecialtyFallback:
    specialty: str
    related: tuple[str, ...]
    why: str


@lru_cache(maxsize=2)
def load_specialty_fallbacks(path: Path = SPECIALTY_FALLBACKS_FILE) -> dict[str, SpecialtyFallback]:
    if not Path(path).exists():
        return {}
    out = {}
    for row in _read(path):
        name = (row.get("specialty") or "").strip()
        if name:
            related = tuple(s.strip() for s in (row.get("related_specialties") or "").split(";") if s.strip())
            out[name] = SpecialtyFallback(name, related, (row.get("why_related") or "").strip())
    return out


def area_tag_names() -> list[str]:
    return [t.tag for t in load_area_tags()]


def count_body_areas(tags: list[str] | set[str]) -> dict:
    """Body areas covered by the symptom tags of one message, after the neighbour pairs.

    Returns {"areas": [...form areas...], "count": n, "merged": [reasons]}; unknown and general tags
    are ignored."""
    by_tag = {t.tag: t for t in load_area_tags()}
    present = {t for t in tags if t in by_tag and by_tag[t].counted}
    areas = sorted({by_tag[t].form_area for t in present})
    parent = {a: a for a in areas}

    def find(a: str) -> str:
        while parent[a] != a:
            a = parent[a]
        return a

    merged = []
    for tags_a, tags_b, because in load_area_neighbours():
        in_a, in_b = present & tags_a, present & tags_b
        if not in_a or not in_b:
            continue
        area_a, area_b = by_tag[next(iter(in_a))].form_area, by_tag[next(iter(in_b))].form_area
        # every tag present in each of the two areas must belong to the pair (heartburn + ear pain: no)
        if any(by_tag[t].form_area == area_a and t not in tags_a for t in present):
            continue
        if any(by_tag[t].form_area == area_b and t not in tags_b for t in present):
            continue
        ra, rb = find(area_a), find(area_b)
        if ra != rb:
            parent[rb] = ra
            merged.append(because)
    groups = sorted({find(a) for a in areas})
    return {"areas": areas, "count": len(groups), "merged": merged}


def validate_mapping() -> list[str]:
    """Problems in specialty_mapping.csv (empty list = valid). Used by tests and the rebuild."""
    problems, seen = [], set()
    form_areas = {r.value for r in mapping_rules("body_area")}
    tag_names = set()
    for tag in load_area_tags():
        if tag.tag in tag_names:
            problems.append(f"body_area_tags: duplicate tag '{tag.tag}'")
        tag_names.add(tag.tag)
        if tag.counted and tag.form_area not in form_areas:
            problems.append(f"body_area_tags '{tag.tag}': form area '{tag.form_area}' is not a body_area answer")
    for tags_a, tags_b, _ in load_area_neighbours():
        for t in tags_a | tags_b:
            if t not in tag_names:
                problems.append(f"body_area_neighbours: unknown tag '{t}'")
    valid = set(specialty_names())
    for fallback in load_specialty_fallbacks().values():
        for name in (fallback.specialty, *fallback.related):
            if name not in valid:
                problems.append(f"specialty_fallbacks: '{name}' is not in specialties.csv")
        if fallback.specialty in fallback.related:
            problems.append(f"specialty_fallbacks: '{fallback.specialty}' lists itself")
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
