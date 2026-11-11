"""Build the doctor review request (PDF) from the project's own data files.

Every table in the PDF is read from the file it describes, so the PDF always matches the data.
Rebuild it after any change to those files:

    PYTHONPATH=src .venv/Scripts/python.exe scripts/build_doctor_review_pdf.py

Output: docs/review/MediRoute_doctor_review.pdf (+ the HTML it is printed from).
Needs Playwright with Chromium (already used for the browser tests).
"""

from __future__ import annotations

import csv
import html
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

from mediroute.utils.paths import DATA_DIR, PROJECT_ROOT, SPECIALTIES_FILE, SPECIALTY_MAPPING_FILE

OUT_DIR = PROJECT_ROOT / "docs" / "review"
SAFETY_FILE = PROJECT_ROOT / "src" / "mediroute" / "specialty_routing" / "step1" / "safety.py"

EMERGENCY_RULES_PLAIN = {
    "chest_pain_with_breathlessness_or_sweating": "Chest pain, tightness or pressure together with breathlessness, sweating, arm pain or jaw pain",
    "stroke_signs": "Face drooping, slurred speech, cannot speak, sudden weakness or numbness, one side of the body affected",
    "unconscious_or_not_breathing": "Unconscious, not breathing, stopped breathing, collapsed, passed out, unresponsive",
    "heavy_bleeding": "Heavy bleeding, vomiting blood, coughing up blood, bleeding that will not stop",
    "suicidal_intent": "Suicidal thoughts: 'ending my life', 'kill myself', 'want to die' (shows a crisis helpline)",
    "seizure_not_stopping": "Seizure that will not stop, continuous fits, status epilepticus",
}
GRETEL_TO_SPECIALTY_NOTE = ("Public test set (gretelai/symptom_to_diagnosis, Apache-2.0): each patient message has a "
                            "diagnosis label; we converted each diagnosis to the speciality a patient should search for.")


def read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def e(value) -> str:
    return html.escape(str(value or ""))


def table(headers: list[str], rows: list[list], widths: list[str] | None = None, answer: bool = True) -> str:
    cols = headers + (["OK / change to"] if answer else [])
    w = (widths or [""] * len(headers)) + (["16%"] if answer else [])
    head = "".join(f'<th style="width:{x}">{e(h)}</th>' if x else f"<th>{e(h)}</th>" for h, x in zip(cols, w))
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + ("<td></td>" if answer else "") + "</tr>"
                   for r in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def questions(items: list[str]) -> str:
    return '<div class="q"><b>Questions for you</b><ol>' + "".join(f"<li>{i}</li>" for i in items) + "</ol></div>"


def section_core50() -> str:
    rows = read(DATA_DIR / "evaluation" / "step1_gold_core50.csv")
    body = []
    for r in rows:
        msg = e(r["query"]) + (f'<div class="report"><b>Report:</b> {e(r["report_text"])}</div>' if r["report_text"] else "")
        flags = []
        if r["expects_clarification"].lower() == "true":
            flags.append("vague: should ask")
        if r["emergency"].lower() == "true":
            flags.append("<b>emergency</b>")
        details = "<br>".join(
            f"{e(k.strip().replace('_', ' ').capitalize())}: {e(v.strip())}"
            for k, _, v in (part.partition("=") for part in r["critical_details"].split(";")) if v.strip())
        body.append([e(r["query_id"]), msg, f"<b>{e(r['expected_specialty'])}</b>", e(r["acceptable_alternatives"].replace(";", "; ")),
                     details, ", ".join(flags)])
    return f"""
<h2 id="s1"><span class="n">1</span> Test cases for speciality routing (50 cases)</h2>
<p class="meta">Priority: <b>critical</b> · about 1–2 hours · file <code>data/evaluation/step1_gold_core50.csv</code></p>
<p>These patient messages were written by our team. For each one we wrote the speciality a patient should
<i>search for</i>. We measure the system against these answers, so if an answer is wrong our accuracy numbers are wrong.
Our evaluator asked for test cases reviewed independently by a clinician.</p>
{questions([
    "<b>Expected speciality:</b> is this the speciality a hospital coordinator should route this patient to?",
    "<b>Also acceptable:</b> are these reasonable too? Is a reasonable one missing?",
    "<b>Critical details:</b> are these the facts that must not be missed (condition, procedure, body part)?",
    "<b>Vague cases:</b> is it right that the system should ask a question instead of answering?",
    "<b>Emergency:</b> should this message show the 'seek emergency care now' notice? Should any other case?",
    "Is any case unrealistic? Mark it 'drop'."])}
{table(["ID", "Patient message", "Expected", "Also acceptable", "Critical details", "Flags"],
       body, ["5%", "33%", "11%", "11%", "18%", "6%"])}
"""


def mapping(source: str) -> list[dict]:
    return [r for r in read(SPECIALTY_MAPPING_FILE) if r["source"] == source]


def names(value: str) -> str:
    return e(value.replace(";", " + "))


def section_ccsr() -> str:
    rows = mapping("ccsr")
    by_system = defaultdict(list)
    for r in rows:
        by_system[r["value"][:3]].append(r)
    defaults = []
    for system, items in by_system.items():
        default = [r for r in items if r["reason"].startswith("body-system default")]
        if default:
            defaults.append([e(system), names(default[0]["specialty"]), str(len(default)),
                             e("; ".join(r["description"] for r in default[:4]) + (" …" if len(default) > 4 else ""))])
    rules = [[e(r["value"]), e(r["description"]), f"<b>{names(r['specialty'])}</b>", e(r["evidence_type"]), e(r["reason"])]
             for r in rows if not r["reason"].startswith("body-system default")]
    return f"""
<h2 id="s2"><span class="n">2</span> Diagnosis group → speciality table (CCSR)</h2>
<p class="meta">Priority: <b>critical</b> · about 1 hour · file <code>data/processed/specialty_mapping.csv</code> (rows with source = ccsr)</p>
<p>To link a diagnosis to a speciality we use AHRQ's <b>Clinical Classifications Software Refined (CCSR)</b>, which groups
every ICD-10-CM diagnosis code into about 540 clinical categories (for example all heart-failure codes → "Heart failure").
We then map each category to one of our 26 specialities. The grouping is AHRQ's; <b>the category → speciality step is ours and
needs your review</b>. Each row also says whether a match is a <i>diagnosis</i> (strong evidence), a <i>symptom</i> (weak
evidence, the system may ask a question) or a <i>status</i> (an encounter, e.g. chemotherapy).</p>
{questions([
    "We have no <b>Rheumatology</b> speciality: rheumatoid arthritis, lupus and gout go to General Medicine (+ Orthopaedics). Acceptable, or should we add Rheumatology?",
    "We have no <b>Vascular Surgery</b> or <b>General Surgery</b>: varicose veins and aneurysms go to Cardiology / Cardiothoracic Surgery; hernia and gallbladder surgery to Gastroenterology. Acceptable, or should we add them?",
    "Injuries: fractures → Orthopaedics; brain and spinal cord injury → Neurosurgery; internal organ injury, wounds and poisoning → Emergency Medicine. Correct?",
    "Symptoms map to the body system they point to (e.g. throat pain and cough → Pulmonology + ENT; abdominal pain → Gastroenterology), as weak evidence. Correct groupings?",
    "Obesity → Bariatric Surgery + Endocrinology; osteoporosis → Endocrinology + Orthopaedics; urinary tract infection → Urology + General Medicine. Correct?",
    "Is any <b>evidence type</b> wrong (a symptom marked as a diagnosis, or the other way round)?"])}
<h3>2a. Default speciality per body system ({len(defaults)} rows)</h3>
<p>Every category in a body system takes this speciality unless it is listed in 2b.</p>
{table(["Body system", "Default speciality", "Categories", "Examples"], defaults, ["9%", "20%", "8%", "47%"])}
<h3>2b. Categories mapped differently from their body system ({len(rules)} rows)</h3>
{table(["Category", "Description", "Speciality", "Evidence", "Our reason"], rules, ["8%", "30%", "18%", "8%", "20%"])}
"""


def section_specialties() -> str:
    rows = read(SPECIALTIES_FILE)
    body = [[f"<b>{e(r['specialty'])}</b>", e(r["description"]), e(r["route_here_when"]), e(r["not_here"])] for r in rows]
    return f"""
<h2 id="s3"><span class="n">3</span> Our list of 26 specialities (the master list)</h2>
<p class="meta">Priority: high · about 30 minutes · file <code>data/processed/specialties.csv</code></p>
<p>The system only ever suggests one of these specialities. The AI model reads the description and the two boundary
columns to choose, so a vague or wrong line leads to wrong suggestions. The boundary columns are new drafts written to
separate neighbouring specialities (the AI most often confused Cardiothoracic Surgery with Cardiology).</p>
{questions([
    "Is any speciality missing that international patients commonly travel to India for (e.g. General Surgery, Vascular Surgery, Rheumatology)?",
    "Is any description or boundary wrong, or likely to mislead (Cardiology vs Cardiothoracic Surgery, Nephrology vs Urology, Organ Transplant vs Hematology)?"])}
{table(["Speciality", "Description", "Route here when", "Not here"], body, ["14%", "24%", "24%", "22%"])}
"""


def section_lay_terms() -> str:
    rows = mapping("lay_term")
    groups = defaultdict(lambda: {"strong": [], "weak": []})
    for r in rows:
        groups[r["specialty"]][r["evidence_type"]].append(r["value"])
    body = [[f"<b>{names(k)}</b>", e(", ".join(sorted(v["strong"]))), e(", ".join(sorted(v["weak"])))]
            for k, v in sorted(groups.items())]
    weak = sum(r["evidence_type"] == "weak" for r in rows)
    return f"""
<h2 id="s4"><span class="n">4</span> Patient words → speciality (lay terms)</h2>
<p class="meta">Priority: high · about 30 minutes · file <code>data/processed/specialty_mapping.csv</code> (rows with source = lay_term)</p>
<p>Patients write "kidney stone" or "red eyes", not ICD terms, so {len(rows)} everyday words point to a speciality.
<b>Strong</b> words name a condition or procedure and count as evidence on their own. <b>Weak</b> words ({weak}) are body
parts, age words, plain symptoms or ambiguous words ("baby", "eye", "bleeding"): they count half and never decide alone.</p>
{questions([
    "Is any word under the wrong speciality?",
    "Is any <b>strong</b> word really ambiguous (should be weak), or any weak word clear enough to be strong?"])}
{table(["Speciality", "Strong words", "Weak words"], body, ["18%", "42%", "26%"])}
"""


def section_emergency() -> str:
    source = SAFETY_FILE.read_text(encoding="utf-8")
    found = re.findall(r'\("([a-z_]+)",\s*\n?\s*\[', source)
    body = [[e(n.replace("_", " ")), e(EMERGENCY_RULES_PLAIN.get(n, "(see safety.py)"))] for n in found]
    return f"""
<h2 id="s5"><span class="n">5</span> Emergency warning rules</h2>
<p class="meta">Priority: high (safety) · about 15 minutes · file <code>src/mediroute/specialty_routing/step1/safety.py</code></p>
<p>Before anything else, fixed rules (never the AI) look for emergency signs. A match shows: "This may be a medical emergency.
Please contact local emergency services or go to the nearest emergency department now."</p>
{questions([
    "Are these the right red flags? Which important ones are missing (e.g. severe allergic reaction, bleeding in pregnancy, high fever in an infant, sudden severe headache, severe abdominal pain)?",
    "Could any rule cause many false alarms?"])}
{table(["Rule", "Triggers when the message mentions"], body, ["24%", "60%"])}
"""


def section_gretel() -> str:
    rows = read(DATA_DIR / "evaluation" / "step1_gold_gretel.csv")
    groups = defaultdict(int)
    for r in rows:
        groups[(r["case_type"].replace("gretel:", ""), r["expected_specialty"], r["acceptable_alternatives"])] += 1
    body = [[e(d), str(n), f"<b>{e(s)}</b>", e(a.replace(";", "; "))] for (d, s, a), n in sorted(groups.items())]
    return f"""
<h2 id="s6"><span class="n">6</span> Public test set: diagnosis → speciality</h2>
<p class="meta">Priority: high · about 15 minutes · file <code>data/evaluation/step1_gold_gretel.csv</code></p>
<p>{e(GRETEL_TO_SPECIALTY_NOTE)} 212 messages in lay language, {len(body)} diagnoses.</p>
{questions([
    "Is the expected speciality right for each diagnosis? Many go to General Medicine; is that how a coordinator would route them?",
    "Varicose veins → Cardiothoracic Surgery: acceptable in India, or another speciality?"])}
{table(["Diagnosis", "Cases", "Expected", "Also acceptable"], body, ["30%", "8%", "22%", "24%"])}
"""


def section_hospital_labels() -> str:
    rows = mapping("hospital")
    pending = [r for r in rows if r["review_status"] != "reviewed"]
    groups = defaultdict(list)
    for r in pending:
        groups[r["specialty"]].append(r["value"])
    order = sorted(groups, key=lambda k: (k == "NONE", k))
    body = [[f"<b>{names(k)}</b>" if k != "NONE" else "<b>NONE</b> (not used for matching)", str(len(groups[k])),
             e("; ".join(sorted(groups[k], key=str.casefold)))] for k in order]
    reviewed = len(rows) - len(pending)
    return f"""
<h2 id="s7"><span class="n">7</span> Hospital department names → our specialities</h2>
<p class="meta">Priority: medium · about 45 minutes · file <code>data/processed/specialty_mapping.csv</code> (rows with source = hospital)</p>
<p>Hospital websites name departments in many ways ("Neurosciences", "Cardiac Sciences", "Joint Replacement"). We map each
name to our specialities to find hospitals for a patient. {len(pending)} names are drafts ({reviewed} were already reviewed).
One name can map to two specialities (e.g. Neurosciences → Neurology + Neurosurgery).</p>
{questions([
    "Is any hospital department name grouped under the wrong speciality?",
    "Should any name marked NONE (not used for matching) point to a speciality?"])}
{table(["Our speciality", "Names", "Hospital department names mapped to it"], body, ["20%", "6%", "58%"])}
"""


def section_cghs() -> str:
    body = [[e("procedure name contains: " + r["value"]), f"<b>{names(r['specialty'])}</b>", e(r["reason"])]
            for r in mapping("cghs_name")]
    body += [[e(r["value"]), f"<b>{names(r['specialty'])}</b>", e(r["reason"])] for r in mapping("cghs_label")]
    return f"""
<h2 id="s8"><span class="n">8</span> Government procedure list (CGHS) → speciality</h2>
<p class="meta">Priority: optional · about 30 minutes · file <code>data/processed/specialty_mapping.csv</code> (rows with source = cghs_name, cghs_label)</p>
<p>The CGHS rate list groups about 1,270 procedures under section labels. We map each label to a speciality so that a
procedure the patient mentions ("TKR", "angioplasty") points to the right department. Name rules are checked first.
NONE = lab tests and other items that say nothing about the speciality.</p>
{table(["CGHS label or rule", "Speciality", "Our note"], body, ["40%", "22%", "22%"])}
"""


CSS = """
@page { size: A4; margin: 16mm 14mm 16mm 14mm; }
body { font-family: "Segoe UI", Arial, sans-serif; font-size: 9.6pt; color: #17201f; line-height: 1.42; }
h1 { font-size: 20pt; margin: 0 0 4px; color: #0b5f59; }
h2 { font-size: 13.5pt; margin: 22px 0 4px; color: #0b5f59; page-break-after: avoid; border-bottom: 1.5px solid #0b5f59; padding-bottom: 3px; }
h3 { font-size: 11pt; margin: 14px 0 4px; page-break-after: avoid; }
.n { display: inline-block; background: #0b5f59; color: #fff; border-radius: 50%; width: 20px; height: 20px; text-align: center; font-size: 10.5pt; line-height: 20px; margin-right: 6px; }
p { margin: 4px 0 8px; }
.meta { color: #4f5f5d; font-size: 9pt; margin-top: 0; }
code { font-family: Consolas, monospace; font-size: 8.4pt; background: #eef3f2; padding: 0 3px; }
table { width: 100%; border-collapse: collapse; margin: 6px 0 10px; font-size: 8.4pt; }
thead { display: table-header-group; }
tr { page-break-inside: avoid; }
th { background: #dcebe9; text-align: left; padding: 4px 5px; border: 1px solid #b8cfcc; }
td { padding: 4px 5px; border: 1px solid #ccdad8; vertical-align: top; }
td:last-child { background: #fbfdfc; }
.report { color: #4f5f5d; font-size: 7.8pt; margin-top: 3px; }
.q { background: #f3f8f7; border-left: 3px solid #0b5f59; padding: 6px 10px; margin: 8px 0; page-break-inside: avoid; }
.q ol { margin: 4px 0 0 18px; padding: 0; } .q li { margin-bottom: 3px; }
.summary td, .summary th { font-size: 9pt; }
.box { border: 1px solid #b8cfcc; padding: 8px 12px; margin: 10px 0; page-break-inside: avoid; }
.pb { page-break-before: always; }
"""


def build_html() -> str:
    today = date.today().strftime("%d %B %Y")
    summary = table(["#", "What to review", "Rows", "Priority", "Time"], [
        ["1", "Test cases for speciality routing", "50", "<b>Critical</b>", "1–2 h"],
        ["2", "Diagnosis group (CCSR) → speciality table", "21 + 161", "<b>Critical</b>", "1 h"],
        ["3", "Our list of 26 specialities: descriptions and boundaries", "26", "High", "30 min"],
        ["4", "Patient words (lay terms) → speciality, strong or weak", "473", "High", "30 min"],
        ["5", "Emergency warning rules", "6", "High (safety)", "15 min"],
        ["6", "Public test set: diagnosis → speciality", "22", "High", "15 min"],
        ["7", "Hospital department names → our specialities", "216 names", "Medium", "45 min"],
        ["8", "Government procedure list (CGHS) → speciality", "76", "Optional", "30 min"],
    ], ["4%", "52%", "12%", "14%", "10%"], answer=False)
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>MediRoute: clinical review request</title>
<style>{CSS}</style></head><body>
<h1>MediRoute: clinical review request</h1>
<p class="meta">Capstone project, PG programme in AI/ML (IIT Bombay) · prepared {today} · draft data, not for clinical use</p>

<div class="box"><b>What MediRoute does.</b> An international patient describes their condition (often with an existing
diagnosis or report). <b>Step 1</b> suggests which medical <b>speciality to search for</b>; <b>Step 2</b> lists Indian hospitals
for that speciality. It is a hospital discovery tool: it does <b>not</b> diagnose, advise treatment or judge urgency, except for
a fixed emergency warning. A doctor at the hospital always confirms the treatment plan.</div>

<p><b>Why we need you.</b> Our evaluator asked that the diagnosis-to-speciality links and the test cases be
<b>reviewed by a clinician</b> rather than written only by engineers. Everything below is our draft. Please mark what is
wrong; you do not need to explain what is right.</p>

<h3>What to review</h3>
{summary}
<p><b>Total:</b> about 4 hours for sections 1–7; sections 1 and 2 matter most if time is short. Sections 2, 4, 7 and 8 are all rows of one file, <code>specialty_mapping.csv</code>.</p>

<h3>How to answer</h3>
<ul>
<li>Write in the last column of each table: leave it empty or write <b>OK</b> if correct, otherwise the <b>change</b>
(e.g. "→ Neurology", "add ENT", "drop"). Comments on the PDF are fine, or edit the CSV files named in each section.</li>
<li>Please add your name and qualification (e.g. "Dr A. Kumar, MD Medicine") so we can record who reviewed it.</li>
<li>Think "where should a hospital coordinator send this patient?", not "what is the diagnosis?".</li>
<li>Later we will send about 20 decisions made by the system's AI judge for a spot check (separate, short).</li>
</ul>
<p>Reviewer: ______________________________ &nbsp; Qualification: ____________________ &nbsp; Date: ______________</p>

<div class="pb"></div>{section_core50()}
<div class="pb"></div>{section_ccsr()}
<div class="pb"></div>{section_specialties()}
<div class="pb"></div>{section_lay_terms()}
{section_emergency()}
<div class="pb"></div>{section_gretel()}
<div class="pb"></div>{section_hospital_labels()}
<div class="pb"></div>{section_cghs()}
<p class="meta" style="margin-top:18px">Thank you. Every table above is generated from the project's data files, so your
corrections go straight back into the system and its evaluation.</p>
</body></html>"""


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    html_path = OUT_DIR / "MediRoute_doctor_review.html"
    pdf_path = OUT_DIR / "MediRoute_doctor_review.pdf"
    html_path.write_text(build_html(), encoding="utf-8")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(html_path.resolve().as_uri(), wait_until="load")
        page.pdf(path=str(pdf_path), format="A4", print_background=True, display_header_footer=True,
                 header_template="<span></span>",
                 footer_template='<div style="font-size:7pt;color:#777;width:100%;text-align:center">'
                                 'MediRoute clinical review request · page <span class="pageNumber"></span> of '
                                 '<span class="totalPages"></span></div>',
                 margin={"top": "14mm", "bottom": "16mm", "left": "13mm", "right": "13mm"})
        browser.close()
    print(f"Wrote {pdf_path}")


if __name__ == "__main__":
    main()
