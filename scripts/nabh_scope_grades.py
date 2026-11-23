"""Treatment grades from the hospitals' NABH "Scope of Accreditation" documents (new Step 2 grading).

The NABH scope is NABH's official list of the clinical services it accredited at a hospital (e.g.
"Nephrology including Dialysis", "Transplantation Services (Liver, Renal, Heart)"). It is independent of
the data Step 2 ranks on (website check + team sheet), so it can judge the ranking without circularity.

    PYTHONPATH=src .venv/Scripts/python.exe scripts/nabh_scope_grades.py fetch   # download + read scopes
    PYTHONPATH=src .venv/Scripts/python.exe scripts/nabh_scope_grades.py grade   # LLM grades, quote-checked

fetch  For every hospital whose nabh_certificate_url is a portal.nabh.co document: download it (one request
       per second; portal.nabh.co has no robots.txt), extract the text (pdftotext), and record the
       certificate number, validity dates and the name printed on it.
       -> data/evaluation/nabh_scope/index.csv, text/<hospital_id>.txt (PDFs in pdf/, not committed)
grade  For every hospital with a scope text, one LLM call grades every need of data/evaluation/step2_gold.csv:
           3  the scope names this procedure or service (or the same thing in other words)
           2  the scope lists the department for this speciality
           1  the scope lists only a related department
           0  the scope lists nothing related
       The grader must quote the scope line it used; code checks the quote is really in the text.
       A grade whose quote is not found is stored as unverified (blank grade = unknown), never guessed.
       -> data/evaluation/step2_scope_grades.csv, log data/evaluation/nabh_scope/grader_calls.jsonl
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path

import requests

from mediroute.utils.paths import DATA_DIR, HOSPITALS_FILE

EVAL = DATA_DIR / "evaluation"
SCOPE_DIR = EVAL / "nabh_scope"
PDF_DIR = SCOPE_DIR / "pdf"
TEXT_DIR = SCOPE_DIR / "text"
INDEX = SCOPE_DIR / "index.csv"
LOG = SCOPE_DIR / "grader_calls.jsonl"
GOLD = EVAL / "step2_gold.csv"
GRADES = EVAL / "step2_scope_grades.csv"
GRADER_MODEL = "openai/gpt-5.6-luna"  # not the portal's model (gpt-6-luna)
USER_AGENT = "Mozilla/5.0 (compatible; MediRoute-capstone-evaluation/1.0; academic research)"
INDEX_COLUMNS = ["hospital_id", "hospital_name", "nabh_status", "certificate_no_data", "certificate_no_document",
                 "name_on_document", "valid_from", "valid_thru", "chars", "fetch_status", "url", "fetched_on"]
GRADE_COLUMNS = ["hospital_id", "hospital_name", "specialty", "procedure", "grade", "quote", "quote_verified",
                 "certificate_no", "note", "grader", "graded_on"]


# --------------------------------------------------------------------------- fetch

def parse_date(text: str) -> str:
    for fmt in ("%B %d, %Y", "%B %d %Y", "%d %B %Y", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text.strip().replace("  ", " "), fmt).date().isoformat()
        except ValueError:
            pass
    return ""


def read_document(text: str) -> dict:
    """Certificate number, validity and hospital name printed on a NABH scope document."""
    cert = re.search(r"Certificate No\.?\s*:?\s*([A-Z]+-[A-Z]*-?\d{4}-\d{3,5})", text)
    valid_from = re.search(r"Valid\s+from\s*:?\s*([A-Za-z]+\s+\d{1,2},?\s+\d{4})", text, re.I)
    valid_thru = re.search(r"Valid\s+(?:thru|through|till|upto|up to)\s*:?\s*([A-Za-z]+\s+\d{1,2},?\s+\d{4})", text, re.I)
    name = ""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for i, line in enumerate(lines):
        if line.lower().startswith("scope of accreditation") and i + 1 < len(lines):
            name = lines[i + 1]
            break
    return {"certificate_no_document": cert.group(1) if cert else "",
            "valid_from": parse_date(valid_from.group(1).replace(",", ",")) if valid_from else "",
            "valid_thru": parse_date(valid_thru.group(1)) if valid_thru else "", "name_on_document": name[:120]}


def cmd_fetch(args) -> None:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    with HOSPITALS_FILE.open(encoding="utf-8-sig", newline="") as f:
        hospitals = list(csv.DictReader(f))
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    rows = []
    for h in hospitals:
        url = h.get("nabh_certificate_url", "")
        if "portal.nabh.co" not in url:
            continue
        hid = h["hospital_id"]
        pdf, txt = PDF_DIR / f"{hid}.pdf", TEXT_DIR / f"{hid}.txt"
        status = "cached"
        if not pdf.exists() or args.refresh:
            try:
                r = session.get(url, timeout=60)
                ok = r.status_code == 200 and r.content[:5] == b"%PDF-"
                status = "downloaded" if ok else f"HTTP {r.status_code} {r.headers.get('content-type', '')[:30]}"
                if ok:
                    pdf.write_bytes(r.content)
            except requests.RequestException as exc:
                status = f"error {type(exc).__name__}"
            time.sleep(1.0)
        text = ""
        if pdf.exists():
            subprocess.run(["pdftotext", str(pdf), str(txt)], check=False, capture_output=True)
            text = txt.read_text(encoding="utf-8", errors="replace") if txt.exists() else ""
            if not text.strip():
                status += "; no text (scanned?)"
        rows.append({"hospital_id": hid, "hospital_name": h["hospital_name"], "nabh_status": h["nabh_status"],
                     "certificate_no_data": h["nabh_certificate_no"], **read_document(text), "chars": len(text),
                     "fetch_status": status, "url": url, "fetched_on": date.today().isoformat()})
        print(f"{hid} {status} {rows[-1]['certificate_no_document']} valid thru {rows[-1]['valid_thru'] or '?'}", flush=True)
    with INDEX.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=INDEX_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} documents -> {INDEX}")


# --------------------------------------------------------------------------- grade

PROMPT = """You read a hospital's NABH accreditation scope (the clinical services NABH accredited there) for an
evaluation data set. Use ONLY the scope text below. No outside knowledge. Copy words exactly as printed.

For each need give three quotes (empty string "" when the scope has nothing for it):
- "department": the scope words naming the department for this speciality, e.g. "Nephrology" for Nephrology,
  "Cardio Thoracic Surgery" / "CTVS" for Cardiothoracic Surgery, "Otorhinolaryngology" for ENT,
  "Medical Oncology" / "Radiation Oncology" for Oncology, "Transplantation Services" for Organ Transplant.
- "service": only when the need has a procedure: the scope words that name THIS procedure or service itself,
  not just the department, e.g. "Dialysis" in "Nephrology including Dialysis", "Joint Replacement" for knee
  replacement, "Renal" in "Transplantation Services (Liver, Renal)" for kidney transplant, "CABG" for bypass,
  "Bariatric" for weight loss surgery. If the scope only names the department, leave "service" empty.
- "related": only when "department" is empty: a related department, e.g. "Cardiology" for a Cardiothoracic
  Surgery need, "Paediatrics" for Pediatric Cardiology.

Hospital: {name}
Scope text:
<<<
{scope}
>>>

Needs (id: speciality | procedure):
{needs}

Answer JSON: "needs": a list with one item per need: {{"id", "department", "service", "related"}}."""

SCHEMA = {"type": "object", "properties": {"needs": {"type": "array", "items": {
    "type": "object", "properties": {"id": {"type": "string"}, "department": {"type": "string"},
                                     "service": {"type": "string"}, "related": {"type": "string"}},
    "required": ["id", "department", "service", "related"]}}}, "required": ["needs"]}


def grade_from_quotes(answer: dict, scope_norm: str, has_procedure: bool) -> tuple[int | None, str, str]:
    """Grade set by code from the quotes that are really in the scope text: (grade, quote, note).
    3 = service quote found and it is not just the department's name (needs with a procedure only);
    2 = department found; 1 = related department only; 0 = nothing; None = a quote not in the text."""
    found = {k: norm(answer.get(k, "")) for k in ("department", "service", "related")}
    missing = [k for k, v in found.items() if v and v not in scope_norm]
    if missing:
        return None, "; ".join(answer.get(k, "") for k in missing), f"quote not in the scope text ({', '.join(missing)})"
    dept, service = found["department"], found["service"]
    if has_procedure and service and service != dept and not (dept and service in dept.split(" ")):
        return 3, f"{answer['service']} [{answer.get('department', '')}]", ""
    if dept:
        return 2, answer["department"], "" if has_procedure or not service else "no procedure asked: max 2"
    if found["related"]:
        return 1, answer["related"], "related department only"
    return 0, "", "nothing related in the scope"


def norm(text: str) -> str:
    """Lower case, letters/digits only, single spaces: survives the PDF's line breaks and bullets."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.casefold()).split())


def needs_from_gold() -> list[tuple[str, str]]:
    with GOLD.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    return sorted({(r["specialty"].strip(), r["procedure"].strip()) for r in rows})


def cmd_grade(args) -> None:
    from mediroute.specialty_routing.step1.ollama_client import OpenRouterClient
    with INDEX.open(encoding="utf-8", newline="") as f:
        index = [r for r in csv.DictReader(f) if int(r["chars"] or 0) > 200]
    if args.only:
        index = [r for r in index if r["hospital_id"] in set(args.only.split(","))]
    needs = needs_from_gold()
    need_lines = "\n".join(f"N{i + 1:02d}: {s} | {p or '-'}" for i, (s, p) in enumerate(needs))
    cache, spent = {}, 0.0
    if LOG.exists():
        for line in LOG.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            spent += rec.get("cost", 0) or 0
            if rec.get("ok"):
                cache[rec["key"]] = rec
    client = OpenRouterClient(model=GRADER_MODEL)
    out, next_call = [], 0.0
    for n, doc in enumerate(index, 1):
        scope = (TEXT_DIR / f"{doc['hospital_id']}.txt").read_text(encoding="utf-8", errors="replace")
        prompt = PROMPT.format(name=doc["hospital_name"], scope=scope.strip()[:12000], needs=need_lines)
        key = hashlib.sha256(f"{GRADER_MODEL}|{prompt}".encode()).hexdigest()[:20]
        rec = cache.get(key)
        if rec is None:
            if spent >= args.budget:
                print(f"budget ${args.budget} reached; stopping before {doc['hospital_id']}")
                break
            for attempt in range(4):
                time.sleep(max(0.0, next_call - time.monotonic()))
                next_call = time.monotonic() + 3.3  # OpenRouter: 20 requests/minute per model
                client._model_down.clear()
                client._down_reason = ""
                call = client.generate_json(prompt, SCHEMA, purpose="nabh_scope_grading")
                if call.ok or "429" not in str(call.error):
                    break
                time.sleep(15 * (attempt + 1))
            cost = float((call.details or {}).get("cost") or 0)
            spent += cost
            rec = {"key": key, "hospital_id": doc["hospital_id"], "ok": call.ok, "parsed": call.parsed,
                   "error": call.error, "cost": cost}
            with LOG.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if not rec.get("ok"):
            print(f"[{n}/{len(index)}] {doc['hospital_id']} FAILED {str(rec.get('error'))[:100]}", flush=True)
            continue
        by_id = {g["id"]: dict(g) for g in (rec["parsed"] or {}).get("needs", [])}
        scope_norm = norm(scope)
        # the department is a property of the speciality, not of one need: use the same (verified) quote for all
        # needs of a speciality, so "Neurosurgery" cannot be the department for one need and "related" for another
        dept_of: dict[str, str] = {}
        for i, (specialty, _) in enumerate(needs):
            d = (by_id.get(f"N{i + 1:02d}") or {}).get("department", "")
            if d and norm(d) in scope_norm:
                dept_of.setdefault(specialty, d)
        for i, (specialty, _) in enumerate(needs):
            g = by_id.get(f"N{i + 1:02d}")
            if g is not None and not g.get("department") and specialty in dept_of:
                g["department"], g["related"] = dept_of[specialty], ""
        counts = {"ok": 0, "unverified": 0, "missing": 0}
        for i, (specialty, procedure) in enumerate(needs):
            g = by_id.get(f"N{i + 1:02d}")
            row = {"hospital_id": doc["hospital_id"], "hospital_name": doc["hospital_name"], "specialty": specialty,
                   "procedure": procedure, "certificate_no": doc["certificate_no_document"] or doc["certificate_no_data"],
                   "grader": f"quotes by LLM ({GRADER_MODEL}) from the NABH scope; grade set by code",
                   "graded_on": date.today().isoformat()}
            if g is None:
                row.update(grade="", quote="", quote_verified="", note="grader gave no answer for this need")
                counts["missing"] += 1
            else:
                grade, quote, note = grade_from_quotes(g, scope_norm, bool(procedure))
                verified = "no" if grade is None else ("yes" if quote else "")
                row.update(grade="" if grade is None else grade, quote=quote, quote_verified=verified, note=note)
                counts["unverified" if grade is None else "ok"] += 1
            out.append(row)
        print(f"[{n}/{len(index)}] {doc['hospital_id']} {counts} spent ${spent:.3f}", flush=True)
    with GRADES.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=GRADE_COLUMNS)
        w.writeheader()
        w.writerows(out)
    print(f"{len(out)} grades for {len({r['hospital_id'] for r in out})} hospitals -> {GRADES}; total spend ${spent:.3f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_fetch = sub.add_parser("fetch")
    p_fetch.add_argument("--refresh", action="store_true", help="download again even if cached")
    p_grade = sub.add_parser("grade")
    p_grade.add_argument("--budget", type=float, default=0.40, help="stop LLM calls beyond this total spend (USD)")
    p_grade.add_argument("--only", default="", help="comma-separated hospital ids (test)")
    args = parser.parse_args()
    {"fetch": cmd_fetch, "grade": cmd_grade}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
