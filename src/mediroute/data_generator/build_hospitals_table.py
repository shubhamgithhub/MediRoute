#!/usr/bin/env python3
"""
Build data/processed/hospitals.csv: the one hospital table Step 1 and Step 2 both read.

Inputs
  data/interim/master-hospital-data.csv     verified rows (NABH / JCI / website), from merge_master
  data/interim/hospital_id_links.csv        master id <-> team 150 sheet id (reviewed matches)
  data/interim/nabh_manual_verification.csv NABH status checked by a person; replaces the master's
                                            automatic NABH match (nabh_match = "manual")
  data/raw/NewMediRoute_Hospital_Dataset_150.xlsx (sheet Hospitals_150)
                                            sub-specialities, procedures, facilities, languages,
                                            cost band and claimed specialities, NOT verified
  data/processed/specialty_mapping.csv      hospital labels -> Step 1 specialities (source = hospital)
  data/processed/cities.csv                 every city must be listed

Rules
  * Identity, accreditation, verification level and verified_specialties come from the master
    (checked against NABH, JCI and the hospital's own website). verified_specialties is the FULL
    website list (the master's specialties_all_found); the master's own verified_specialties keeps
    only the top 6 for its Excel sheet, which hid real departments from Step 2 (checked against the
    Step 2 website grades: recall 0.54 -> 0.78 with precision 0.94 -> 0.90).
  * The team sheet only adds detail columns, marked by detail_source = "team 150 sheet (not
    verified)". Its accreditation / "Verified" values are not used: they disagree with the
    master for 10-14 of 49 shared hospitals and say "Verified" for all 150.
  * team_claimed_specialties = the team sheet's specialities + sub-specialities, normalised.
    Step 2 may use them for eligibility but must say they are unverified.

Usage
  python -m mediroute.data_generator.build_hospitals_table
"""
from __future__ import annotations

import csv
import sys
from collections import Counter

import pandas as pd

from mediroute.common.locations import city_names
from mediroute.common.specialties import hospital_label_map, specialty_names
from mediroute.utils.paths import (
    HOSPITAL_LINKS_FILE,
    HOSPITAL_MASTER_FILE,
    HOSPITALS_FILE,
    HOSPITAL_SCHEMA_FILE,
    NABH_MANUAL_FILE,
    TEAM_150_SHEET_FILE,
)

NABH_STATUSES = {"Accredited", "Needs verification", "Not found in NABH directory"}


def load_nabh_manual(path=NABH_MANUAL_FILE) -> dict[str, dict]:
    """hospital_id -> a person's NABH check (data/interim/nabh_manual_verification.csv)."""
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        return {r["hospital_id"].strip(): r for r in csv.DictReader(f) if r.get("hospital_id", "").strip()}


def apply_nabh_manual(row: dict, check: dict) -> None:
    """A person's NABH check replaces the master's automatic NABH match for this hospital.
    Team rule (2026-11-22): NABH Entry Level counts as Accredited; nabh_level keeps the difference."""
    row["nabh_status"] = check["nabh_status"].strip()
    row["nabh_certificate_no"] = check.get("nabh_certificate_no", "").strip()
    row["nabh_listed_name"] = check.get("nabh_listed_name", "").strip()
    row["nabh_certificate_url"] = check.get("evidence_url", "").strip()
    row["nabh_match"] = "manual"
    note = (f"NABH checked by {check.get('checked_by', '').strip() or 'team'} on {check.get('checked_on', '').strip()}"
            f" ({check.get('nabh_level', '').strip() or 'level not recorded'}): {check.get('note', '').strip()}")
    kept = [n for n in row.get("notes", "").split(" | ") if n and not n.startswith("NABH")]
    row["notes"] = " | ".join(kept + [note])

SCHEMA_FILE = HOSPITAL_SCHEMA_FILE
TEAM_SHEET = "Hospitals_150"
TEAM_DETAIL = "team 150 sheet (not verified)"


def clean(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    return "" if text.lower() in ("nan", "na", "none") else text


def clean_list(value) -> str:
    """'CABG; TAVR; ' -> 'CABG; TAVR' (keeps the team's wording, drops empty items)."""
    return "; ".join(x.strip() for x in clean(value).split(";") if x.strip())


def load_normalization() -> dict[str, set[str]]:
    """Hospital label (casefolded) -> specialities; NONE labels are known with an empty set."""
    return {label: set(names) for label, names in hospital_label_map().items()}


def normalise(labels: str, mapping: dict[str, set[str]], unmapped: Counter) -> list[str]:
    out: set[str] = set()
    for raw in labels.split(";"):
        raw = raw.strip()
        if not raw:
            continue
        hit = mapping.get(raw.casefold())
        if hit is None:
            unmapped[raw] += 1
        else:
            out |= hit
    return sorted(out)


def build(out_path=HOSPITALS_FILE) -> list[dict]:
    with open(SCHEMA_FILE, newline="", encoding="utf-8-sig") as f:
        columns = [r["column_name"] for r in sorted(csv.DictReader(f), key=lambda r: int(r["column_order"]))]
    master = pd.read_csv(HOSPITAL_MASTER_FILE, dtype=str, keep_default_na=False)
    team = pd.read_excel(TEAM_150_SHEET_FILE, sheet_name=TEAM_SHEET, dtype=str).set_index("hospital_id")
    with open(HOSPITAL_LINKS_FILE, newline="", encoding="utf-8-sig") as f:
        links = list(csv.DictReader(f))
    team_by_master = {r["hospital_id"]: r["team150_id"] for r in links}
    added_from_team = {r["hospital_id"] for r in links if r["link_method"].startswith("added from")}
    mapping = load_normalization()
    nabh_manual = load_nabh_manual()
    unmapped: Counter = Counter()

    rows = []
    for _, m in master.iterrows():
        row = {c: clean(m.get(c)) for c in columns if c in master.columns}
        if row["hospital_id"] in nabh_manual:
            apply_nabh_manual(row, nabh_manual[row["hospital_id"]])
        if clean(m.get("specialties_all_found")):  # full website list, not the master's top 6
            row["verified_specialties"] = clean(m.get("specialties_all_found"))
        tid = team_by_master.get(row["hospital_id"], "")
        t = team.loc[tid] if tid and tid in team.index else None
        row["team150_id"] = tid
        row["record_origin"] = "team 150 sheet" if row["hospital_id"] in added_from_team else "team city lists"
        if t is not None:
            claimed = normalise(clean(t.get("verified_specialties")) + ";" + clean(t.get("verified_subspecialties")),
                                mapping, unmapped)
            row.update(team_claimed_specialties=";".join(claimed),
                       subspecialties=clean_list(t.get("verified_subspecialties")),
                       procedures=clean_list(t.get("verified_procedures")),
                       facilities=clean_list(t.get("verified_facilities")),
                       languages=clean(t.get("languages_or_interpreter_support")),
                       detail_source=TEAM_DETAIL)
            if not row.get("cost_band_inr") and clean(t.get("cost_band_inr")):
                row["cost_band_inr"] = clean(t.get("cost_band_inr"))
        for c in columns:
            row.setdefault(c, "")
        if row.get("cost_band_inr") == "":
            row["cost_band_inr"] = "NA"
        rows.append(row)

    # ---- checks: one speciality list, one city list, unique ids
    canon, cities = set(specialty_names()), set(city_names())
    problems = []
    for r in rows:
        for col in ("verified_specialties", "team_claimed_specialties"):
            bad = [s for s in r[col].split(";") if s.strip() and s.strip() != "NA" and s.strip() not in canon]
            if bad:
                problems.append(f"{r['hospital_id']}: {col} not in Step 1 list: {bad}")
        if r["city"] not in cities:
            problems.append(f"{r['hospital_id']}: city '{r['city']}' not in data/processed/cities.csv")
    known = {r["hospital_id"] for r in rows}
    for hid, check in nabh_manual.items():
        if hid not in known:
            problems.append(f"{NABH_MANUAL_FILE.name}: {hid} is not in the master")
        if check.get("nabh_status", "").strip() not in NABH_STATUSES:
            problems.append(f"{NABH_MANUAL_FILE.name}: {hid} nabh_status {check.get('nabh_status')!r} "
                            f"not in {sorted(NABH_STATUSES)}")
    ids = Counter(r["hospital_id"] for r in rows)
    problems += [f"duplicate hospital_id {i}" for i, n in ids.items() if n > 1]
    if unmapped:
        problems.append(f"team labels missing from specialty_mapping.csv (source = hospital): {dict(unmapped)}")
    if problems:
        print("\n".join(problems[:40]))
        sys.exit("hospitals.csv NOT written; fix the problems above")

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)
    return rows


def main() -> None:
    rows = build()
    def names(value: str) -> set[str]:
        return {s.strip() for s in value.split(";") if s.strip() and s.strip() != "NA"}

    verified = Counter(s for r in rows for s in names(r["verified_specialties"]))
    either = Counter(s for r in rows for s in names(r["verified_specialties"]) | names(r["team_claimed_specialties"]))
    print(f"Wrote {len(rows)} hospitals in {len({r['city'] for r in rows})} cities -> {HOSPITALS_FILE}")
    print(f"  with team detail (procedures etc.): {sum(1 for r in rows if r['detail_source'])}")
    print(f"  {'speciality':<36}{'verified':>9}{'incl. team':>11}")
    for name in specialty_names():
        print(f"  {name:<36}{verified[name]:>9}{either[name]:>11}")


if __name__ == "__main__":
    main()
