"""Synthetic medical-report PDFs for testing the report upload (text-based PDFs; OCR is out of scope).

    PYTHONPATH=src python scripts/make_synthetic_reports.py

Writes data/evaluation/synthetic_reports/<case>/*.pdf and manifest.csv. Every PDF says
"SYNTHETIC - NOT A REAL PATIENT"; names, IDs, phone numbers and e-mails are invented.

Cases
  R01-R15  the 15 core50 report cases on a lab letterhead (expected speciality from the gold set)
  L01-L08  realistic layouts: department list in the letterhead, lab tables, two columns, a long
           discharge summary with the diagnosis on page 4, typos, contact details on every page,
           a second unrelated report, report only (nothing typed)
  E01-E08  edge cases: empty file, password-protected, over 10 MB, renamed text file, 6 files,
           two conflicting reports, a scanned page next to typed text, a scanned page only
"""
from __future__ import annotations

import csv
import random
import shutil
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import benchmark_step1 as bench  # noqa: E402

from mediroute.utils.paths import DATA_DIR  # noqa: E402

OUT = DATA_DIR / "evaluation" / "synthetic_reports"
SYNTH = "SYNTHETIC REPORT - NOT A REAL PATIENT - FOR SOFTWARE TESTING ONLY"
CSS = """
body { font-family: sans-serif; font-size: 10pt; color: #111; }
.lh { border-bottom: 2px solid #234; padding-bottom: 4px; margin-bottom: 6px; }
.lh b { font-size: 14pt; color: #234; } .small { font-size: 8pt; color: #555; }
table { border-collapse: collapse; width: 100%; } td, th { border: 1px solid #999; padding: 2px 4px; font-size: 9pt; }
h3 { font-size: 11pt; margin: 8px 0 4px; } .synth { color: #a00; font-size: 8pt; }
"""
FAKE_PATIENTS = [("Asha Verma", 54, "F"), ("Ravi Kumar", 67, "M"), ("Meena Iyer", 45, "F"), ("Arjun Shah", 38, "M"),
                 ("Fatima Khan", 29, "F"), ("Vikram Rao", 61, "M"), ("Lakshmi Nair", 72, "F"), ("Imran Ali", 4, "M")]


def letterhead(name="SYNTHETIC DIAGNOSTICS LAB", sub="Plot 00, Test Nagar, Pune 411000 · NABL ID: TEST-0000",
               depts: str = "") -> str:
    d = f'<div class="small">{depts}</div>' if depts else ""
    return f'<div class="lh"><b>{name}</b><div class="small">{sub}</div>{d}</div>'


def patient_block(i: int, contact: bool = False) -> str:
    name, age, sex = FAKE_PATIENTS[i % len(FAKE_PATIENTS)]
    extra = (f"<br>Phone: +91 98765 4{i:04d} · E-mail: {name.split()[0].lower()}.test{i}@example.com · "
             f"Aadhaar: 1234 5678 {9000 + i}") if contact else ""
    return (f'<table><tr><td>Patient: {name} (synthetic)</td><td>Age/Sex: {age}/{sex}</td>'
            f'<td>Lab ID: SYN-{1000 + i}</td></tr></table><div class="small">{extra}</div>')


def html_page(body: str) -> str:
    return f'<html><body>{body}<p class="synth">{SYNTH}</p></body></html>'


def pdf_from_pages(pages: list[str], path: Path, password: str | None = None, footer: str = "") -> None:
    doc = pymupdf.open()
    for html in pages:
        page = doc.new_page(width=595, height=842)  # A4 in points
        page.insert_htmlbox(pymupdf.Rect(40, 40, 555, 790), html, css=CSS)
        if footer:
            page.insert_text((40, 815), footer, fontsize=7, color=(0.35, 0.35, 0.35))
    path.parent.mkdir(parents=True, exist_ok=True)
    if password:
        doc.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw=password + "-owner", user_pw=password)
    else:
        doc.save(path)
    doc.close()


def scanned_copy(src: Path, dst: Path, dpi: int = 110) -> None:
    """Image-only PDF: each page rendered to a picture (what a phone scan looks like to a parser)."""
    source, out = pymupdf.open(src), pymupdf.open()
    for page in source:
        pix = page.get_pixmap(dpi=dpi)
        new = out.new_page(width=page.rect.width, height=page.rect.height)
        new.insert_image(new.rect, pixmap=pix)
    out.save(dst)
    source.close()
    out.close()


def report_body(title: str, report_text: str) -> str:
    lines = "<br>".join(line.strip() for line in report_text.splitlines() if line.strip())
    return f"<h3>{title}</h3><p>{lines}</p><p class='small'>Reported by: Dr. Test Radiologist (synthetic), MD</p>"


def title_for(text: str) -> str:
    first = text.strip().splitlines()[0]
    return first.split(":")[0][:60] if ":" in first else first[:60]


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    core = {g["query_id"]: g for g in bench.load_gold("core50") if g["report_text"].strip()}
    rows: list[dict] = []

    def add(case, category, typed, files, expected="", alternatives="", outcome="route", notes=""):
        rows.append({"case_id": case, "category": category, "typed_text": typed,
                     "files": ";".join(str(f.relative_to(OUT)).replace("\\", "/") for f in files),
                     "expected_specialty": expected, "acceptable_alternatives": alternatives,
                     "expected_outcome": outcome, "notes": notes})

    # R01-R15: the core50 report cases ------------------------------------------------------------
    for n, (qid, g) in enumerate(sorted(core.items()), 1):
        case = f"R{n:02d}"
        path = OUT / case / f"{qid}_report.pdf"
        pdf_from_pages([html_page(letterhead() + patient_block(n) + report_body(title_for(g["report_text"]), g["report_text"]))], path)
        add(case, "core report", g["query"], [path], g["expected_specialty"], ";".join(g["alternatives"]),
            notes=f"core50 {qid}")

    c = {k: core[k] for k in core}
    # L01: letterhead lists many departments (noise words) ------------------------------------------
    p = OUT / "L01" / "biopsy_hospital_letterhead.pdf"
    depts = ("Departments: Cardiology · Neurology · Orthopaedics · Nephrology · Gastroenterology · Urology · "
             "Paediatrics · Oncology · ENT · Ophthalmology · 24x7 Emergency")
    pdf_from_pages([html_page(letterhead("SYNTHETIC MULTISPECIALITY HOSPITAL", depts=depts) + patient_block(11)
                              + report_body("HISTOPATHOLOGY REPORT", c["C023"]["report_text"]))], p)
    add("L01", "letterhead noise", "Biopsy report attached.", [p], "Oncology", notes="department list in the letterhead")

    # L02: lab panel as a table ----------------------------------------------------------------------
    p = OUT / "L02" / "kidney_lab_panel.pdf"
    rows_tbl = [("Haemoglobin", "8.9", "g/dL", "12-16"), ("Serum creatinine", "6.8", "mg/dL", "0.6-1.2"),
                ("Blood urea", "142", "mg/dL", "15-40"), ("eGFR", "8", "mL/min/1.73m2", ">90"),
                ("Potassium", "5.9", "mmol/L", "3.5-5.1"), ("Sodium", "136", "mmol/L", "135-145"),
                ("Calcium", "7.8", "mg/dL", "8.5-10.5"), ("Phosphorus", "6.4", "mg/dL", "2.5-4.5")]
    tbl = "<table><tr><th>Test</th><th>Result</th><th>Unit</th><th>Reference</th></tr>" + "".join(
        f"<tr><td>{a}</td><td><b>{b}</b></td><td>{u}</td><td>{r}</td></tr>" for a, b, u, r in rows_tbl) + "</table>"
    pdf_from_pages([html_page(letterhead() + patient_block(12) + "<h3>RENAL FUNCTION PANEL</h3>" + tbl +
                              "<p>USG: bilateral small contracted kidneys.<br>IMPRESSION: End-stage renal disease. "
                              "On maintenance haemodialysis twice weekly.</p>")], p)
    add("L02", "lab table", "These are my kidney reports.", [p], "Nephrology", "Organ Transplant", notes="values in a table")

    # L03: two-column layout -------------------------------------------------------------------------
    p = OUT / "L03" / "knee_mri_two_column.pdf"
    two_col = ('<table style="border:none"><tr><td style="width:35%;border:none;font-size:8pt;color:#555">'
               "SYNTHETIC IMAGING CENTRE<br>3T MRI · CT · X-ray · USG<br>Timings 8 am - 10 pm<br>Home sample collection<br>"
               "Accredited test centre</td><td style='border:none'>" + report_body("MRI LEFT KNEE", c["C022"]["report_text"])
               + "</td></tr></table>")
    pdf_from_pages([html_page(patient_block(13) + two_col)], p)
    add("L03", "two columns", c["C022"]["query"], [p], "Orthopaedics", notes="side column with centre details")

    # L04: long discharge summary, diagnosis on page 4 (tests the 6,000-character cut) -----------------
    p = OUT / "L04" / "long_discharge_summary.pdf"
    rnd = random.Random(4)
    filler_words = ("patient was observed vitals stable monitored hydration oral intake encouraged mobilised physiotherapy "
                    "nursing care reviewed bloods repeated tolerated diet ward round family counselled sleep comfortable "
                    "pain score charted fluid balance maintained").split()

    def filler(n):
        return " ".join(rnd.choice(filler_words) for _ in range(n)).capitalize() + "."
    pages = []
    for day in range(1, 4):
        body = (letterhead("SYNTHETIC GENERAL HOSPITAL") + patient_block(14) + f"<h3>DISCHARGE SUMMARY - page {day}</h3>"
                + "".join(f"<p><b>Day {day*3 + k}:</b> {filler(80)}</p>" for k in range(3)))
        pages.append(html_page(body))
    pages.append(html_page(letterhead("SYNTHETIC GENERAL HOSPITAL") + "<h3>FINAL DIAGNOSIS</h3>"
                           "<p>Coronary angiography: triple vessel disease (LAD 90%, LCx 80%, RCA 70%).<br>"
                           "<b>Final diagnosis: Triple vessel coronary artery disease.</b><br>"
                           "Plan: referred for coronary artery bypass grafting (CABG).</p>"))
    pdf_from_pages(pages, p)
    add("L04", "long report", "Discharge summary of my father is attached.", [p], "Cardiothoracic Surgery", "Cardiology",
        notes="diagnosis only on page 4, after ~3 pages of daily notes")

    # L05: typos and abbreviations --------------------------------------------------------------------
    p = OUT / "L05" / "brain_mri_typos.pdf"
    pdf_from_pages([html_page(letterhead("SYNTH NEURO IMAGING") + patient_block(15) + report_body(
        "MRI BRAIN W/ CONTRAST", "lmpression: ring enhancing lesion lt fronta1 lobe w/ perilesional oedema, "
        "likely high grade gl ioma (? GBM).\nNeurosurgica1 opinion advsd. Pt c/o headache x 2 mths."))], p)
    add("L05", "typos", "brain scan resullt", [p], "Neurosurgery", "Oncology", notes="OCR-like typos, abbreviations")

    # L06: contact details on every page (privacy check) ---------------------------------------------
    p = OUT / "L06" / "echo_with_contacts.pdf"
    pdf_from_pages([html_page(letterhead("SYNTHETIC HEART CLINIC", sub="Helpline +91 20 5555 0000 · clinic@example.com")
                              + patient_block(16, contact=True) + report_body("ECHOCARDIOGRAPHY", c["C032"]["report_text"]))],
                   p, footer="Patient phone +91 98765 40016 · patient.test16@example.com · Aadhaar 1234 5678 9016")
    add("L06", "privacy", "my fathers heart report", [p], "Cardiology",
        notes="phone, e-mail and Aadhaar-like ID must not reach the log")

    # L07: the relevant report plus a routine normal one -----------------------------------------------
    p1, p2 = OUT / "L07" / "thyroid_fnac.pdf", OUT / "L07" / "routine_cbc_normal.pdf"
    pdf_from_pages([html_page(letterhead() + patient_block(17) + report_body("USG NECK + FNAC", c["C028"]["report_text"]))], p1)
    pdf_from_pages([html_page(letterhead() + patient_block(17) + "<h3>COMPLETE BLOOD COUNT</h3>"
                              "<table><tr><th>Test</th><th>Result</th><th>Reference</th></tr>"
                              "<tr><td>Haemoglobin</td><td>13.1 g/dL</td><td>12-16</td></tr>"
                              "<tr><td>WBC</td><td>7,200 /uL</td><td>4,000-11,000</td></tr>"
                              "<tr><td>Platelets</td><td>2.4 lakh/uL</td><td>1.5-4.5 lakh</td></tr></table>"
                              "<p>IMPRESSION: Within normal limits.</p>")], p2)
    add("L07", "two reports, one relevant", "Thyroid report attached.", [p1, p2], "Oncology", "Endocrinology;ENT",
        notes="second report is a normal blood count")

    # L08: report only, nothing typed ------------------------------------------------------------------
    p = OUT / "L08" / "fertility_tests.pdf"
    pdf_from_pages([html_page(letterhead("SYNTHETIC FERTILITY LAB") + patient_block(18) + report_body("FERTILITY WORK-UP", c["C029"]["report_text"]))], p)
    add("L08", "report only", "", [p], "Reproductive Medicine", "Obstetrics & Gynaecology", notes="no typed text")

    # E01-E08: edge cases ---------------------------------------------------------------------------
    p = OUT / "E01" / "empty.pdf"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"")
    add("E01", "empty file", "Report attached.", [p], outcome="api_error", notes="0-byte file: expect a clear error")

    p = OUT / "E02" / "knee_mri_password.pdf"
    pdf_from_pages([html_page(letterhead() + patient_block(21) + report_body("MRI LEFT KNEE", c["C022"]["report_text"]))],
                   p, password="test1234")
    add("E02", "password-protected", "My scan report is attached. What kind of specialist should I look for?", [p],
        outcome="unreadable_notice", notes="password-protected: expect 'cannot read this file'")

    p = OUT / "E03" / "too_large.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    # random pixels do not compress: two 2200x2200 images give a file of about 29 MB
    noise = random.Random(3).randbytes(2200 * 2200 * 3)
    big = pymupdf.Pixmap(pymupdf.csRGB, 2200, 2200, noise, False)
    for k in range(2):
        page.insert_image(pymupdf.Rect(0, k * 400, 595, k * 400 + 400), pixmap=big)
    page.insert_text((40, 820), SYNTH, fontsize=7)
    p.parent.mkdir(parents=True)
    doc.save(p, deflate=False)
    doc.close()
    add("E03", "too large", "Big scan attached.", [p], outcome="api_error", notes=f"{p.stat().st_size / 1e6:.1f} MB > 10 MB limit")

    p = OUT / "E04" / "not_really_a.pdf"
    p.parent.mkdir(parents=True)
    p.write_text("This is a plain text file renamed to .pdf\nDIAGNOSIS: osteoarthritis knee\n", encoding="utf-8")
    add("E04", "renamed text file", "My report.", [p], outcome="api_error", notes="not a PDF inside")

    six = []
    for k in range(6):
        p = OUT / "E05" / f"report_{k + 1}.pdf"
        pdf_from_pages([html_page(letterhead() + patient_block(22) + report_body("MRI LEFT KNEE", c["C022"]["report_text"]))], p)
        six.append(p)
    add("E05", "too many files", "Six reports attached.", six, outcome="api_error", notes="limit is 5 files")

    p1, p2 = OUT / "E06" / "child_echo_vsd.pdf", OUT / "E06" / "child_hearing_bera.pdf"
    pdf_from_pages([html_page(letterhead() + patient_block(7) + report_body("2D ECHO", c["C026"]["report_text"]))], p1)
    pdf_from_pages([html_page(letterhead() + patient_block(7) + report_body("BERA", c["C030"]["report_text"]))], p2)
    add("E06", "two conflicting reports", "Reports of my son attached.", [p1, p2], "Pediatric Cardiology",
        "ENT;Cardiothoracic Surgery", outcome="route_or_ask", notes="heart defect + hearing loss: one answer or a question")

    src = OUT / "E07" / "_typed_source.pdf"
    pdf_from_pages([html_page(letterhead() + patient_block(23) + report_body("HISTOPATHOLOGY", c["C023"]["report_text"]))], src)
    p = OUT / "E07" / "biopsy_scanned.pdf"
    scanned_copy(src, p)
    src.unlink()
    add("E07", "scanned + typed text", "Biopsy report attached.", [p], outcome="unreadable_notice",
        notes="scan (OCR out of scope): expect the patient to be told the file could not be read")

    p = OUT / "E08" / "biopsy_scanned_only.pdf"
    p.parent.mkdir(parents=True)
    shutil.copy(OUT / "E07" / "biopsy_scanned.pdf", p)
    add("E08", "scanned only", "", [p], outcome="unreadable_notice", notes="scan and nothing typed: ask for a readable file")

    with (OUT / "manifest.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} cases, {sum(len(r['files'].split(';')) for r in rows)} files -> {OUT}")


if __name__ == "__main__":
    main()
