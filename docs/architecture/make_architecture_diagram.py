"""MediRoute flow diagram: every step top to bottom, what kind of logic it is, and the data it reads.

    python docs/architecture/make_architecture_diagram.py

Writes mediroute_pipeline_architecture.html (the source) and mediroute_pipeline_architecture.png next to
this file (README section 2 shows the PNG). Colours: LLM · ML search (embeddings / TF-IDF / FAISS) ·
deterministic code and rules · data · input / output. Edit STEP1 / STEP2 below when the pipeline changes.
The previous diagrams are kept as mediroute_pipeline_architecture_v1.png (hand-made) and in git history.
"""
from __future__ import annotations

from html import escape as e
from pathlib import Path

HERE = Path(__file__).resolve().parent

# (kind, title, what happens, checks by code, data used)
# kinds: llm | ml | code | io
INPUT = ("io", "Patient input", "Text in their own words (English) · optional PDF reports (text-based) · city or state", "", [])
REPORTS = ("code", "Read reports", "PyMuPDF extracts the text of each PDF; scans, locked or damaged files are skipped and the "
           "patient is told why (no OCR, no translation)", "max 5 files, 10 MB each; text cut at 6,000 characters", [])
STEP1 = [
    ("code", "1 · Protect", "Remove phone numbers, e-mails and ID numbers before anything is stored or sent", "", []),
    ("code", "2 · Emergency check", "Fixed red-flag rules (crushing chest pain, stroke signs, suicidal words…) → emergency notice "
     "on top; routing continues", "", ["Emergency rules (safety.py)"]),
    ("llm", "3 · Extract evidence", "LLM copies the conditions, procedures and body parts from the text",
     "kept only if the phrase is really in the text; generic words dropped",
     ["Model: GPT-6 Luna (OpenRouter) or local Ollama", "Lay terms (specialty_mapping.csv)"]),
    ("ml", "4a · Lookup voter", "Keyword (TF-IDF) + meaning (MiniLM embeddings) search of each phrase, fused (RRF); "
     "symptom-type evidence counts half", "", ["step1_lookup.csv: 10,884 entries from ICD-10-CM via AHRQ CCSR, CGHS procedures, lay terms",
                                               "Lookup embeddings (vector_store/)"]),
    ("llm", "4b · LLM voter", "LLM picks 1 of the 26 specialities (or “unclear”) using each one's route-here / not-here rules",
     "closed list: any other answer is ignored", ["specialties.csv: 26 specialities with boundaries"]),
    ("code", "5 · Decide", "Both voters agree → answer. They disagree → the patient's body-area answer, if it fits only one. "
     "Otherwise → judge", "General Medicine asks once before it is accepted", ["Body-area rules (specialty_mapping.csv)"]),
    ("llm", "5b · LLM judge (disagreements only)", "LLM chooses between the two candidates, citing evidence lines",
     "closed choice · cited evidence must exist and support it · quote must be in the text · asked twice with the order "
     "swapped; any failed check → ask", ["Model: GPT-6 Luna", "Evidence lines from step1_lookup.csv"]),
    ("code", "6 · Ask (when unsure)", "One short form (body area, diagnosis, procedure; never repeated), then a short list of "
     "2–4 candidates with descriptions", "", ["specialties.csv (descriptions)"]),
]
STEP1_OUT = ("io", "Suggested speciality to search", "Speciality + evidence words + disclaimer (not a diagnosis)", "", [])
STEP2 = [
    ("code", "1 · Eligible hospitals", "Hospitals whose speciality list includes it (own website = verified; team sheet = "
     "marked unverified) and that are in the chosen area", "", ["hospitals.csv: 201 hospitals checked against NABH, JCI and their websites",
                                                               "Hospital labels (specialty_mapping.csv)", "cities.csv: search areas"]),
    ("ml", "2 · Similarity search", "FAISS search with multi-qa-MiniLM: the patient's speciality, diagnoses and procedures vs "
     "each hospital's services; top 3×k", "", ["Hospital index (vector_store/hospital_index.faiss)"]),
    ("code", "3 · Transparent bonuses", "+ website-confirmed speciality, matching procedure, verified details, NABH, JCI, "
     "international services (total ≤ 0.20); each bonus becomes a reason", "", ["hospitals.csv"]),
    ("code", "4 · Outside-area group", "Fewer than 3 in the area → add the same state, then the rest of India, as a separate "
     "labelled group", "", ["cities.csv (states)"]),
]
STEP2_OUT = ("io", "Recommended hospitals", "Top 5 with the reasons for each · no LLM at run time in Step 2", "", [])
TRACE = ("code", "Trace for every request", "Input (redacted), LLM prompts and answers, votes, judge, decision, timings → admin page",
         "", ["logs/step1_trace.jsonl"])

KIND = {"llm": ("LLM", "#efeafe", "#7c6bd6"), "ml": ("ML search", "#e6f1fd", "#3f86d4"),
        "code": ("Deterministic code / rules", "#e7f5ec", "#3f9a65"), "io": ("Input / output", "#fff3e0", "#d9932f")}


def row(step) -> str:
    kind, title, what, checks, data = step
    label, bg, border = KIND[kind]
    chk = f'<div class="chk">✔ {e(checks)}</div>' if checks else ""
    chips = "".join(f'<div class="data">{e(d)}</div>' for d in data) or '<div class="none">—</div>'
    return (f'<div class="row"><div class="box" style="background:{bg};border-color:{border}">'
            f'<div class="kind" style="color:{border}">{e(label)}</div><b>{e(title)}</b><div>{e(what)}</div>{chk}</div>'
            f'<div class="link"></div><div class="datacol">{chips}</div></div>')


def arrow() -> str:
    return '<div class="arrow">▼</div>'


def group(title: str, steps) -> str:
    inner = arrow().join(row(s) for s in steps)
    return f'<div class="group"><div class="gtitle">{e(title)}</div>{inner}</div>'


def build() -> str:
    legend = "".join(f'<span class="lg"><i style="background:{bg};border-color:{bd}"></i>{e(lb)}</span>'
                     for lb, bg, bd in KIND.values())
    legend += '<span class="lg"><i style="background:#f3f2ef;border-color:#a39d92"></i>Data used</span>'
    body = (row(INPUT) + arrow() + row(REPORTS) + arrow() + group("STEP 1 · patient words → speciality to search", STEP1)
            + arrow() + row(STEP1_OUT) + arrow() + group("STEP 2 · speciality → ranked hospitals", STEP2)
            + arrow() + row(STEP2_OUT) + '<div class="sep"></div>' + row(TRACE))
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>MediRoute flow</title><style>
body{{margin:0;background:#fff;font-family:"Segoe UI",Arial,sans-serif;color:#1d2733}}
.wrap{{width:1320px;padding:28px 36px}} h1{{font-size:26px;margin:0 0 6px;color:#1e2a5a}}
.sub{{color:#5b6676;font-size:14px;margin-bottom:14px}} .legend{{display:flex;gap:22px;margin:0 0 18px;font-size:14px}}
.lg i{{display:inline-block;width:16px;height:16px;border:2px solid;border-radius:4px;vertical-align:-3px;margin-right:6px}}
.head{{display:grid;grid-template-columns:780px 40px 1fr;font-size:13px;font-weight:700;color:#6a7584;letter-spacing:.6px;margin-bottom:6px}}
.row{{display:grid;grid-template-columns:780px 40px 1fr;align-items:center}}
.box{{border:2px solid;border-radius:10px;padding:10px 14px;font-size:14.5px;line-height:1.4}}
.box b{{font-size:16px;display:block;margin-bottom:2px}} .kind{{font-size:11px;font-weight:800;letter-spacing:.8px;text-transform:uppercase}}
.chk{{margin-top:5px;font-size:13px;color:#3d6b4f}}
.link{{height:2px;background:#c9c4ba;margin:0 4px}} .datacol{{display:flex;flex-direction:column;gap:5px}}
.data{{background:#f3f2ef;border:1.5px solid #a39d92;border-radius:7px;padding:5px 10px;font-size:13.5px}}
.none{{color:#b0aaa0;font-size:13px;padding-left:6px}}
.arrow{{width:780px;text-align:center;color:#8a93a0;font-size:16px;line-height:22px}}
.group{{border:2px dashed #b9bfcc;border-radius:14px;padding:10px 12px 12px;margin:2px -14px}}
.gtitle{{font-weight:800;color:#1e2a5a;font-size:15px;margin:0 0 8px;letter-spacing:.4px}}
.group .row{{grid-template-columns:766px 40px 1fr}} .group .arrow{{width:766px}}
.sep{{height:16px}}
</style></head><body><div class="wrap">
<h1>MediRoute: how a request flows</h1>
<div class="sub">Two separate steps. Purple = an LLM; blue = ML search (embeddings, TF-IDF, FAISS); green = fixed code and rules.
Every LLM output is checked by code before it is used. Right column = the data each step reads.</div>
<div class="legend">{legend}</div>
<div class="head"><span>STEP</span><span></span><span>DATA USED</span></div>
{body}
</div></body></html>"""


def main() -> None:
    html_path = HERE / "mediroute_pipeline_architecture.html"
    html_path.write_text(build(), encoding="utf-8")
    stale = HERE / "mediroute_pipeline_architecture.svg"  # the previous generated format
    if stale.exists():
        stale.unlink()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900}, device_scale_factor=1.5)
        page.goto(html_path.resolve().as_uri(), wait_until="load")
        page.locator(".wrap").screenshot(path=str(HERE / "mediroute_pipeline_architecture.png"))
        browser.close()
    print(f"Wrote {html_path.name} and mediroute_pipeline_architecture.png")


if __name__ == "__main__":
    main()
