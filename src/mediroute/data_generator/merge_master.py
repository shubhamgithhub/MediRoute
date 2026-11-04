#!/usr/bin/env python3
"""
Combine per-city outputs of build_hospital_master into the master hospital CSV and
validate every row against data/processed/hospital.schema.csv.

Usage:
  python -m mediroute.data_generator.merge_master
  python -m mediroute.data_generator.merge_master --in-dir data/interim/master --out data/processed/master-hospital-data.csv
"""
import argparse
import csv
import re
import sys
from pathlib import Path

from mediroute.utils.paths import INTERIM_DATA_DIR, PROCESSED_DATA_DIR

SCHEMA_FILE = PROCESSED_DATA_DIR / "hospital.schema.csv"
DEFAULT_OUT = PROCESSED_DATA_DIR / "master-hospital-data.csv"


def load_schema(path=SCHEMA_FILE):
    with open(path, newline="", encoding="utf-8-sig") as f:
        cols = sorted(csv.DictReader(f), key=lambda r: int(r["column_order"]))
    return cols


def allowed_set(spec):
    """'Tier 1|Tier 2' -> {'Tier 1','Tier 2'}; free-text specs (URLs, patterns) -> None."""
    v = spec["allowed_values"].strip()
    if spec["data_type"] != "category" and spec["column_name"] not in ("city", "nabh_match"):
        return None
    return {x.strip() for x in v.split("|")} if v else None


def validate(rows, schema):
    errors = []
    ids = {}
    for i, r in enumerate(rows, start=2):
        rid = r.get("hospital_id", "?")
        for spec in schema:
            col, val = spec["column_name"], (r.get(spec["column_name"]) or "").strip()
            if spec["required"] == "yes" and not val and col not in ("official_source_url",):
                errors.append(f"line {i} {rid}: '{col}' is empty")
            allowed = allowed_set(spec)
            if allowed and val and val not in allowed:
                errors.append(f"line {i} {rid}: '{col}'='{val}' not in {sorted(allowed)}")
        if not re.fullmatch(r"H\d{3}", rid):
            errors.append(f"line {i}: hospital_id '{rid}' does not match H###")
        if rid in ids:
            errors.append(f"line {i}: duplicate hospital_id {rid} (also line {ids[rid]})")
        ids[rid] = i
    return errors


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in-dir", default=str(INTERIM_DATA_DIR / "master"))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    schema = load_schema()
    cols = [s["column_name"] for s in schema]
    files = sorted(Path(args.in_dir).glob("*_master.csv"))
    if not files:
        sys.exit(f"no *_master.csv files in {args.in_dir}")
    rows = []
    for p in files:
        with open(p, newline="", encoding="utf-8-sig") as f:
            part = list(csv.DictReader(f))
        missing = [c for c in cols if part and c not in part[0]]
        if missing:
            sys.exit(f"{p.name} lacks schema columns {missing}; rebuild it with build_hospital_master --force")
        rows.extend(part)
        print(f"{p.name}: {len(part)} rows")
    rows.sort(key=lambda r: r["hospital_id"])

    errors = validate(rows, schema)
    if errors:
        print(f"\n{len(errors)} schema problems:")
        for e in errors[:50]:
            print("  " + e)
        sys.exit("master NOT written; fix the problems above")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote {len(rows)} hospitals ({len({r['city'] for r in rows})} cities) -> {out}")


if __name__ == "__main__":
    main()
