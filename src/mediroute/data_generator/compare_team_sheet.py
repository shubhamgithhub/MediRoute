#!/usr/bin/env python3
"""
Compare what a team member entered in Hosp_Data_Final.xlsx with what build_hospital_master
verified, field by field, and write a CSV of agreements and disagreements.

Usage:
  python -m mediroute.data_generator.compare_team_sheet --sheet RaviTeja
"""
import argparse
import csv
from collections import Counter
from pathlib import Path

from openpyxl import load_workbook

from mediroute.utils.paths import GENERATOR_INPUT_DIR, INTERIM_DATA_DIR

FIELDS = ["nabh_status", "jci_status", "international_patient_service"]


def norm(field, value):
    """Map free-text team values and pipeline values onto comparable buckets."""
    v = (value or "").strip().lower()
    if field in ("nabh_status", "jci_status"):
        if v in ("accredited", "certified", "empaneled"):
            return "yes"
        if v in ("not listed", "not found in nabh directory", "not applicable", "no"):
            return "no"
        return "unsure"  # 'needs verification', blanks
    if field == "international_patient_service":
        return "yes" if v == "available" else "no" if v in ("na", "no", "not found on website", "") else "unsure"
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", required=True)
    ap.add_argument("--workbook", default=str(GENERATOR_INPUT_DIR / "Hosp_Data_Final.xlsx"))
    ap.add_argument("--master-dir", default=str(INTERIM_DATA_DIR / "master"))
    args = ap.parse_args()

    ws = load_workbook(args.workbook, data_only=True)[args.sheet]
    rows = [r for r in ws.iter_rows(values_only=True) if any(v not in (None, "") for v in r)]
    head = [str(h).strip() if h else "" for h in rows[0]]
    team = {str(d["hospital_id"]).strip(): d for d in (dict(zip(head, r)) for r in rows[1:])}

    verified = {}
    for p in Path(args.master_dir).glob("*_master.csv"):
        with open(p, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                verified[r["hospital_id"]] = r

    out_rows, tally = [], Counter()
    for hid, t in team.items():
        v = verified.get(hid)
        if not v:
            out_rows.append({"hospital_id": hid, "hospital_name": t["hospital_name"], "field": "*",
                             "team_value": "", "verified_value": "", "result": "not run"})
            continue
        for fld in FIELDS:
            a, b = norm(fld, str(t.get(fld) or "")), norm(fld, v[fld])
            if a == "unsure":
                result = f"team unsure -> pipeline says {b}"
            elif a == b:
                result = "agree"
            else:
                result = "DISAGREE"
            tally[(fld, result.split(" ->")[0])] += 1
            out_rows.append({"hospital_id": hid, "hospital_name": t["hospital_name"], "field": fld,
                             "team_value": t.get(fld) or "", "verified_value": v[fld], "result": result,
                             "evidence": (v.get("nabh_certificate_no") if fld == "nabh_status" else
                                          v.get("jci_listed_name") if fld == "jci_status" else
                                          v.get("url_Internantional_patients")),
                             "notes": v.get("notes", "")})
    out = Path(args.master_dir) / f"{args.sheet.lower()}_comparison.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["hospital_id", "hospital_name", "field", "team_value",
                                          "verified_value", "result", "evidence", "notes"])
        w.writeheader()
        w.writerows(out_rows)
    for (fld, res), n in sorted(tally.items()):
        print(f"{fld:32} {res:20} {n}")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
