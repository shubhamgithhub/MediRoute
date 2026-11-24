"""MediRoute final report (PDF, A4 landscape, one slide-sized topic per page, ready to turn into slides).

    PYTHONPATH=src python scripts/build_final_report_pdf.py

Writes docs/report/MediRoute_final_report.html and .pdf. Live numbers are read from the runs named on
each page: the doctor-reviewed core50 run (newest core50-only portal run) and the 24 Nov portal
regression; the other numbers are the measured results recorded in the team report
(docs/report/MediRoute_team_report.pdf), cited per page.

Screenshots go in docs/report/assets/: patient_form.png (taken by this script from the local
portal if it is running) and cloudwatch_dashboard.png (add it by hand from the AWS console).
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
OUT_DIR = ROOT / "docs" / "report"
ASSETS = OUT_DIR / "assets"
EVAL = ROOT / "data" / "evaluation"
REGRESSION_RUN = EVAL / "portal_runs" / "20261124_195435"  # core50 + mediroute, 24 Nov, gpt-6-luna

# chart colours (dataviz reference palette, slots 1 and 2, validated together) + neutral ink
BLUE, ORANGE, GREY = "#2a78d6", "#eb6834", "#c9c7bf"
INK, MUTED, GRID = "#1d1d1b", "#6b6a64", "#e6e4dc"


# ------------------------------------------------------------------------------------------ data
def gold_ok(name: str) -> dict:
    rows = csv.DictReader((EVAL / f"step1_gold_{name}.csv").open(encoding="utf-8-sig"))
    return {r["query_id"]: {r["expected_specialty"], *[a for a in r["acceptable_alternatives"].split(";") if a]}
            for r in rows}


def run_rows(run: Path) -> list[dict]:
    return [json.loads(line) for line in (run / "results.jsonl").read_text(encoding="utf-8").splitlines()]


def first_answer(rows: list[dict], ok: dict, gold_set: str) -> dict:
    c = {"n": 0, "correct": 0, "wrong": 0, "asks": 0, "after": 0}
    for r in rows:
        if r["gold_set"] != gold_set:
            continue
        good = ok[r["query_id"]]
        first = r["specialty"]
        final = r.get("specialty2") if first is None and "decision2" in r else first
        c["n"] += 1
        c["asks" if first is None else "correct" if first in good else "wrong"] += 1
        c["after"] += final in good
    return c


def doctor_run() -> Path:
    runs = [d for d in sorted((EVAL / "portal_runs").iterdir()) if (d / "meta.json").exists()
            and json.loads((d / "meta.json").read_text(encoding="utf-8")).get("sets") == "core50=50"]
    return runs[-1]


# ------------------------------------------------------------------------------------------ html helpers
def table(headers, rows, widths=None, cls=""):
    cols = "".join(f'<col style="width:{w}">' for w in widths) if widths else ""
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f'<table class="{cls}"><colgroup>{cols}</colgroup><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def bullets(items):
    return "<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>"


def tiles(items):
    return '<div class="tiles">' + "".join(
        f'<div class="tile"><b>{a}</b><span>{b}</span><small>{c}</small></div>' for a, b, c in items) + "</div>"


def page(title, body, kicker="", source=""):
    k = f'<div class="kicker">{kicker}</div>' if kicker else ""
    s = f'<div class="source">{source}</div>' if source else ""
    return f'<section class="slide">{k}<h1>{title}</h1><div class="body">{body}</div>{s}</section>'


def box(title, sub, kind):
    return f'<div class="box {kind}"><b>{title}</b><span>{sub}</span></div>'


def row_of(boxes):
    out = []
    for i, b in enumerate(boxes):
        out.append(b)
        if i < len(boxes) - 1:
            out.append('<div class="arrow">→</div>')
    return '<div class="flow">' + "".join(out) + "</div>"


# ------------------------------------------------------------------------------------------ charts (inline SVG)
def stacked_chart(rows, title, width=1000, label_w=330, highlight=()):
    """100% stacked horizontal bars: correct (blue) · confidently wrong (orange) · asks (grey).
    rows = [(label, correct, wrong, asks)] in percent."""
    bar_h, gap, top = 22, 12, 54
    plot_w = width - label_w - 170
    h = top + len(rows) * (bar_h + gap) + 34
    p = [f'<svg viewBox="0 0 {width} {h}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Segoe UI, Arial" role="img" aria-label="{title}">',
         f'<text x="0" y="16" font-size="15" font-weight="600" fill="{INK}">{title}</text>']
    lx = label_w
    for name, col in (("Correct", BLUE), ("Confidently wrong", ORANGE), ("Asks the patient", GREY)):
        p.append(f'<rect x="{lx}" y="28" width="12" height="12" rx="2" fill="{col}"/>'
                 f'<text x="{lx + 18}" y="38" font-size="12" fill="{MUTED}">{name}</text>')
        lx += 160
    for t in range(0, 101, 25):
        x = label_w + plot_w * t / 100
        p.append(f'<line x1="{x}" x2="{x}" y1="{top - 4}" y2="{h - 30}" stroke="{GRID}"/>'
                 f'<text x="{x}" y="{h - 14}" font-size="11" fill="{MUTED}" text-anchor="middle">{t}%</text>')
    for i, (label, correct, wrong, asks) in enumerate(rows):
        y = top + i * (bar_h + gap)
        weight = "700" if label in highlight else "400"
        p.append(f'<text x="{label_w - 12}" y="{y + 15}" font-size="12.5" font-weight="{weight}" fill="{INK}" text-anchor="end">{label}</text>')
        x = label_w
        for value, col in ((correct, BLUE), (wrong, ORANGE), (asks, GREY)):
            w = plot_w * value / 100
            if w > 0:
                p.append(f'<rect x="{x}" y="{y}" width="{max(w - 2, 0.5)}" height="{bar_h}" rx="3" fill="{col}"/>')
            x += w
        p.append(f'<text x="{label_w + plot_w * correct / 100 - 6}" y="{y + 15}" font-size="11.5" font-weight="600" fill="#fff" text-anchor="end">{correct:.0f}%</text>')
        tail = f"{wrong:.0f}% wrong · {asks:.0f}% asks"
        p.append(f'<text x="{width - 2}" y="{y + 15}" font-size="11" fill="{MUTED}" text-anchor="end">{tail}</text>')
    p.append("</svg>")
    return "".join(p)


def bar_chart(rows, title, width=480, label_w=210, vmax=1.0, fmt="{:.2f}"):
    """Horizontal bars, one measure; rows = [(label, value, highlighted, (lo, hi) or None)]."""
    bar_h, gap, top = 22, 12, 34
    plot_w = width - label_w - 50
    h = top + len(rows) * (bar_h + gap) + 30
    p = [f'<svg viewBox="0 0 {width} {h}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Segoe UI, Arial" role="img" aria-label="{title}">',
         f'<text x="0" y="16" font-size="14" font-weight="600" fill="{INK}">{title}</text>']
    for t in (0, 0.25, 0.5, 0.75, 1.0):
        x = label_w + plot_w * t
        p.append(f'<line x1="{x}" x2="{x}" y1="{top - 4}" y2="{h - 26}" stroke="{GRID}"/>'
                 f'<text x="{x}" y="{h - 10}" font-size="10.5" fill="{MUTED}" text-anchor="middle">{fmt.format(t * vmax)}</text>')
    for i, (label, value, hi, ci) in enumerate(rows):
        y = top + i * (bar_h + gap)
        col = BLUE if hi else GREY
        p.append(f'<text x="{label_w - 10}" y="{y + 15}" font-size="12" font-weight="{700 if hi else 400}" fill="{INK}" text-anchor="end">{label}</text>')
        w = plot_w * value / vmax
        p.append(f'<rect x="{label_w}" y="{y}" width="{w}" height="{bar_h}" rx="3" fill="{col}"/>')
        end = label_w + w
        if ci:
            x0, x1 = label_w + plot_w * ci[0] / vmax, label_w + plot_w * ci[1] / vmax
            p.append(f'<line x1="{x0}" x2="{x1}" y1="{y + bar_h / 2}" y2="{y + bar_h / 2}" stroke="{INK}" stroke-width="1.5"/>'
                     f'<line x1="{x0}" x2="{x0}" y1="{y + 6}" y2="{y + bar_h - 6}" stroke="{INK}" stroke-width="1.5"/>'
                     f'<line x1="{x1}" x2="{x1}" y1="{y + 6}" y2="{y + bar_h - 6}" stroke="{INK}" stroke-width="1.5"/>')
            end = max(end, x1)
        p.append(f'<text x="{end + 6}" y="{y + 15}" font-size="11.5" font-weight="600" fill="{INK}">{fmt.format(value)}</text>')
    p.append("</svg>")
    return "".join(p)


def paired_chart(rows, title, a_name, b_name, width=1000, label_w=330):
    """Two series per row (percent): a = general AI (orange), b = MediRoute (blue)."""
    bar_h, inner, gap, top = 16, 3, 16, 54
    plot_w = width - label_w - 70
    h = top + len(rows) * (2 * bar_h + inner + gap) + 30
    p = [f'<svg viewBox="0 0 {width} {h}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Segoe UI, Arial" role="img" aria-label="{title}">',
         f'<text x="0" y="16" font-size="15" font-weight="600" fill="{INK}">{title}</text>',
         f'<rect x="{label_w}" y="28" width="12" height="12" rx="2" fill="{ORANGE}"/><text x="{label_w + 18}" y="38" font-size="12" fill="{MUTED}">{a_name}</text>',
         f'<rect x="{label_w + 200}" y="28" width="12" height="12" rx="2" fill="{BLUE}"/><text x="{label_w + 218}" y="38" font-size="12" fill="{MUTED}">{b_name}</text>']
    for t in range(0, 101, 25):
        x = label_w + plot_w * t / 100
        p.append(f'<line x1="{x}" x2="{x}" y1="{top - 4}" y2="{h - 26}" stroke="{GRID}"/>'
                 f'<text x="{x}" y="{h - 10}" font-size="10.5" fill="{MUTED}" text-anchor="middle">{t}%</text>')
    for i, (label, a, b) in enumerate(rows):
        y = top + i * (2 * bar_h + inner + gap)
        p.append(f'<text x="{label_w - 12}" y="{y + bar_h + 5}" font-size="12.5" fill="{INK}" text-anchor="end">{label}</text>')
        for j, (v, col) in enumerate(((a, ORANGE), (b, BLUE))):
            yy = y + j * (bar_h + inner)
            w = plot_w * v / 100
            p.append(f'<rect x="{label_w}" y="{yy}" width="{w}" height="{bar_h}" rx="3" fill="{col}"/>'
                     f'<text x="{label_w + w + 6}" y="{yy + 12}" font-size="11" font-weight="600" fill="{INK}">{v:.0f}%</text>')
    p.append("</svg>")
    return "".join(p)


def image(path: Path, alt: str, placeholder: str, cls="shot"):
    if path.exists():
        return f'<img src="{path.as_uri()}" alt="{alt}" class="{cls}">'
    return f'<div class="placeholder">{placeholder}<br><code>{path.relative_to(ROOT)}</code></div>'


# ------------------------------------------------------------------------------------------ pages
def p_title():
    return f"""<section class="slide title">
<div class="kicker">AI/ML in Practice · Capstone · PG programme, IIT Bombay · Team T09</div>
<h1 class="big">MediRoute</h1>
<p class="tag">Healthcare beyond borders: from a patient's own words to the right speciality and verified Indian hospitals</p>
<p class="team">Anand Chavan · Aniket More · Pravin Patil · RaviTeja Karri · Shubham Thakare</p>
<p class="muted">Final report · {date.today():%d %B %Y}</p>
<p class="disclaimer">Academic project. MediRoute is a hospital discovery tool: it does not diagnose or advise treatment; a doctor at the hospital confirms the plan.</p>
</section>"""


def p_idea():
    body = f"""<div class="cols">
<div><h2>The problem: medical tourism to India</h2>
{bullets([
    "International patients (and their families) travel to India for affordable, high-quality treatment: cardiac surgery, joint replacement, transplants, cancer care, IVF.",
    "Researching where to go is <b>fragmented</b>: hospital information is scattered, listed generically and <b>not matched to the patient's diagnosis or report</b>.",
    "Report review is manual (a human agent reads it), and the hospital data on aggregator sites is curated by the platform, not grounded in verifiable public sources.",
])}
<h2>Users</h2>
{bullets(["<b>Primary:</b> international patients and caregivers researching treatment.", "<b>Secondary (future):</b> hospitals receiving enquiries."])}
</div>
<div><h2>What MediRoute does</h2>
{bullets([
    "The patient writes the need <b>in their own words</b>, optionally attaches PDF reports, and picks a city or state.",
    "<b>Step 1</b> suggests <b>which speciality to search for</b>, with the evidence words and a question when unsure.",
    "<b>Step 2</b> lists <b>NABH / JCI-verified hospitals</b> for that speciality in the area, each with the reasons it was chosen.",
    "Emergency and crisis messages get a fixed safety notice first.",
])}
<h2>What it does not do</h2>
{bullets(["No diagnosis, no treatment advice, no booking.", "Scope narrowed after the mid-term review: translation, currency, PDF summary and the hospital agent were deferred to put the effort into evaluation."])}
</div></div>"""
    return page("Idea and use case", body, "1 · Idea",
                "Mid-term report (4 Oct 2026) and TA feedback, docs/base/")


def p_use_case():
    shot = image(ASSETS / "patient_form.png", "Patient form", "Screenshot of the patient form", "shot small")
    body = f"""<div class="cols wide-left">
<div><h2>A request, end to end (real portal request)</h2>
{table(["", "What happens"], [
    ["Patient writes", "“I have kidney stones and severe pain in my lower back” · city: Mumbai"],
    ["Step 1 evidence", "AI copies <i>kidney stones</i>, <i>severe pain</i>, <i>lower back</i>; code checks each phrase is really in the text"],
    ["Step 1 votes", "Medical lookup (ICD-10 / CCSR) → Urology · LLM voter → Urology → they agree"],
    ["Step 1 answer", "<b>Suggested speciality to search: Urology</b> + the evidence words + disclaimer (2.2 s)"],
    ["Step 2", "NABH-verified Mumbai hospitals that list Urology, ranked by similarity + transparent bonuses, top 5 with reasons"],
], ["22%", "78%"])}
<h2>When it is not sure, it asks</h2>
{bullets([
    "“I am having sciatic nerve pain since 3 months”: lookup says Neurology, LLM says Orthopaedics → the AI judge cannot confirm → <b>one question</b> (body area) → “Bones, joints and muscles” → Orthopaedics.",
    "Vague messages (“pain”, “I need surgery in India”) always get a question instead of a guess.",
])}</div>
<div>{shot}</div></div>"""
    return page("Use case: what the patient sees", body, "1 · Idea", "Worked examples from the portal trace (team report, section 3)")


def p_architecture():
    step1 = row_of([
        box("Protect + emergency rules", "redact IDs; red flags → Emergency Medicine (no AI)", "code"),
        box("Extract evidence", "LLM copies conditions, procedures, body parts; code keeps only words really in the text", "ai"),
        box("Two independent voters", "Lookup: TF-IDF + MiniLM search of 10,884 ICD-10 / CCSR / CGHS entries · LLM: picks 1 of 26", "ml"),
        box("Decide", "agree → answer · disagree → guarded LLM judge · unsure → ask the patient", "ai"),
    ])
    step2 = row_of([
        box("Eligible hospitals", "lists the speciality, in the chosen city / area / state", "code"),
        box("Similarity", "FAISS + multi-qa-MiniLM: need vs hospital services", "ml"),
        box("Transparent bonuses", "NABH, JCI, website-confirmed, procedure match (≤ 0.20); each becomes a reason", "code"),
        box("Top 5 + reasons", "outside-area group if fewer than 3 in the area", "out"),
    ])
    body = f"""
<div class="legend"><span class="sw ai"></span> LLM (generative AI) <span class="sw ml"></span> ML search (embeddings, TF-IDF, FAISS) <span class="sw code"></span> fixed code and rules <span class="sw out"></span> output</div>
<div class="stage"><div class="stage-title">Input</div>{box("Patient text + optional PDF reports + city / state", "PyMuPDF reads text PDFs (no OCR); a report about another problem does not override the typed text", "out")}</div>
<div class="stage"><div class="stage-title">Step 1 · patient words → speciality to search</div>{step1}</div>
<div class="stage"><div class="stage-title">Step 2 · speciality → ranked verified hospitals (no LLM at run time)</div>{step2}</div>
{bullets([
    "<b>Two steps, kept separate:</b> each has its own test set and metrics, so a fault can be traced to one step.",
    "<b>LLM:</b> GPT-6 Luna (OpenRouter) for evidence, voter and judge; ~2–4 small calls per request. <b>ML:</b> local MiniLM embeddings, TF-IDF, FAISS. Orchestrated with LangGraph behind a FastAPI API.",
    "<b>Step 2 uses no LLM</b> because we measured it: an LLM capability judge ranked worse (NDCG@5 0.66) than filter + similarity + bonuses (0.71).",
])}"""
    return page("Architecture: two simple steps", body, "2 · Architecture", "src/mediroute/specialty_routing (Step 1), src/mediroute/hospital_recommendation (Step 2)")


def p_ai_use():
    body = f"""
{table(["Where", "AI / ML used", "Why", "Guardrail (code)"], [
    ["Step 1 · evidence", "<b>LLM</b> copies conditions, procedures, body parts; tags body areas", "Patients write freely (“sugar problem”, “heart is weak”); lifts lookup accuracy 87–88% → 93%", "Phrase kept only if ≥ 60% of its words are in the text: the AI cannot invent evidence"],
    ["Step 1 · lookup voter", "<b>ML search</b>: TF-IDF + MiniLM embeddings over ICD-10-CM / CCSR / CGHS, fused by rank", "Grounded in public medical coding data, explainable", "Only the 26 fixed specialities can come out"],
    ["Step 1 · LLM voter", "<b>LLM</b> picks 1 of 26 using each speciality's “route here when / not here” rules", "Understands context the lookup misses", "Closed list (JSON schema); it never sees the lookup's answer (independent votes)"],
    ["Step 1 · judge", "<b>LLM</b> chooses between the two candidates, only when they disagree (~20%)", "Fewer questions to the patient (biggest single gain: 66% → 82% correct)", "Must cite a lookup evidence line and a quote from the text; asked twice in swapped order; any failure → ask"],
    ["Safety net", "<b>LLM</b> quotes self-harm words the rules missed", "Misspellings, other languages", "Can only add the crisis message, never remove one; fixed rules decide emergencies"],
    ["Step 2 · ranking", "<b>ML search</b>: FAISS + multi-qa-MiniLM similarity", "Patient wording differs from hospital wording", "Eligibility by verified speciality first; bonuses are visible reasons"],
], ["14%", "30%", "28%", "28%"], "small")}
<p class="note"><b>Principle:</b> the LLM is never trusted on its own. Every AI output is checked by code; when the checks fail, MediRoute asks the patient instead of guessing.</p>"""
    return page("Where AI is used, and how it is kept honest", body, "2 · Architecture")


def p_data():
    body = f"""<div class="cols">
<div><h2>Medical knowledge (public, versioned)</h2>
{table(["Source", "What we use", "Size"], [
    ["ICD-10-CM (CDC)", "diagnosis codes and names, searchable", "9,170 entries"],
    ["AHRQ CCSR", "groups ICD-10 codes into clinical categories → mapped to our specialities", "547 rules"],
    ["CGHS rate list (Govt. of India)", "procedure names (bypass, TKR, cataract…)", "1,270 entries"],
    ["Lay terms (team)", "everyday wording: “kidney stones”, “sugar problem”", "444 entries"],
    ["Specialities (team, doctor-reviewed)", "26 specialities with “route here when / not here” boundaries", "26"],
], ["30%", "52%", "18%"], "small")}
<p class="muted">→ one Step 1 lookup of <b>10,884 entries</b> and <b>1,381</b> mapping rules (data/processed/).</p>
</div>
<div><h2>Hospitals (manually extracted and verified)</h2>
{bullets([
    "<b>200 hospitals</b> in <b>60 cities, 24 states</b>; collected by the team city by city (team sheet + candidate lists per member), then each one checked by hand and script.",
    "<b>NABH</b> directory: 130 accredited (certificate and scope document linked); <b>JCI</b>: 66; hospital's own website read for the <b>full speciality list</b>; 97 offer international-patient services.",
    "Real vs simulated kept apart: fields from the team sheet are marked “not verified”; costs were removed from the screens.",
    "<b>NABH “Scope of Accreditation”</b> PDFs (136 hospitals) used as an independent source to grade hospitals in the Step 2 benchmark.",
])}
<h2>Test data</h2>
{bullets(["<b>Doctor-reviewed core50</b> (ground truth) · mediroute 84 lay messages · gretel 212 (public symptom set) · unseen 110 (written by another model) · Step 2: 45 graded requests · safety 30 · report mismatch 25."])}
</div></div>"""
    return page("Datasets", body, "3 · Data", "data/processed/step1_lookup.csv, specialty_mapping.csv, hospitals.csv; data/evaluation/")


def p_eval_design():
    body = f"""
{table(["Layer", "Test set", "What it checks", "Labels"], [
    ["Step 1", "<b>core50</b>: 50 cases (diagnosis, report, procedure, noisy report, vague, emergency, children)", "speciality routing on hard situations", "<b>doctor-reviewed and signed</b> (23 Nov 2026)"],
    ["Step 1", "mediroute: 84 short lay-language messages", "everyday wording", "team draft"],
    ["Step 1", "<b>unseen</b>: 110 messages written by a model MediRoute does not use (Mistral Large 4)", "over-fitting: cases we never tuned on", "by construction"],
    ["Step 2", "45 requests (big city, procedure, state, small city, rare speciality)", "hospital ranking", "graded 0–3 from the official NABH scope"],
    ["Both", "general AI (Gemini 4 Carbon) on the same requests", "value beyond a chatbot", "same labels"],
    ["Safety", "30 crisis / red-flag / injection cases; 25 report-vs-text cases", "guardrails", "team"],
], ["8%", "44%", "26%", "22%"], "small")}
<div class="cols">
<div><h2>Step 1 metrics</h2>{bullets([
    "<b>Correct</b>: expected speciality or an accepted alternative.",
    "<b>Confidently wrong</b>: answered and wrong: the costly error we minimise.",
    "<b>Asks</b>: asked the patient; <b>correct after one answer</b>: where the patient ends up.",
])}</div>
<div><h2>Step 2 metrics (the patient sees 5)</h2>{bullets([
    "<b>P@5</b> (precision): share of the 5 shown that are good.",
    "<b>NDCG@5</b>: good hospitals near the top; <b>Hit@1</b>: the first is good; <b>Bad@5</b>: an unsuitable one is shown.",
    "Baselines + bootstrap 95% CI + paired permutation test.",
])}</div></div>"""
    return page("Evaluation design", body, "4 · Evaluation", "Three layers as asked by the TA: gold data, baselines, an independent model")


def p_step1_evolution():
    rows = [
        ("1 · Keyword search only", 86, 14, 0), ("2 · Meaning search only", 92, 8, 0), ("3 · LLM only", 76, 16, 8),
        ("4 · 3 voters, majority (old app)", 80, 2, 18), ("5 · Hybrid lookup + LLM, ask on disagreement", 68, 2, 30),
        ("6 · 5 + clean data (CCSR, lay terms)", 66, 0, 34), ("7 · 6 + guarded LLM judge", 82, 2, 16),
        ("8 · 7 + speciality boundaries (adopted)", 86, 2, 12),
    ]
    run = doctor_run()
    c = first_answer(run_rows(run), gold_ok("core50"), "core50")
    rows.append(("Today, real portal, doctor labels", 100 * c["correct"] / c["n"], 100 * c["wrong"] / c["n"], 100 * c["asks"] / c["n"]))
    chart = stacked_chart(rows, "Step 1 on core50: each design change, one at a time", highlight={rows[7][0], rows[-1][0]})
    body = f"""{chart}
{bullets([
    "<b>Baselines first</b> (rows 1–3): simple search looks accurate but is confidently wrong on 8–16% of cases; an LLM alone is the worst (16%).",
    "<b>Design choice:</b> two independent voters and <b>ask when they disagree</b> → confident errors fall to 0–2% but too many questions (rows 5–6).",
    "The <b>guarded LLM judge</b> and the speciality boundaries win back the answers (rows 7–8). Today, on the doctor's labels: <b>0 confidently wrong</b>.",
])}"""
    return page("Step 1: how the design evolved", body, "4 · Evaluation · Step 1",
                f"Offline runs 11–12 Nov (rows 1–8, scored again on the doctor's labels: unchanged); last row: portal run {run.name}")


def p_doctor():
    run = doctor_run()
    rows = run_rows(run)
    gold = {r["query_id"]: r for r in csv.DictReader((EVAL / "step1_gold_core50.csv").open(encoding="utf-8-sig"))}
    ok = gold_ok("core50")
    c = first_answer(rows, ok, "core50")
    by: dict[str, dict] = {}
    for r in rows:
        t = gold[r["query_id"]]["case_type"].replace("_", " ")
        d = by.setdefault(t, {"n": 0, "correct": 0, "wrong": 0, "asks": 0})
        d["n"] += 1
        d["asks" if r["specialty"] is None else "correct" if r["specialty"] in ok[r["query_id"]] else "wrong"] += 1
    ms = sorted(r["client_ms"] for r in rows if r.get("client_ms"))
    body = f"""
{tiles([(f"{c['correct'] / c['n']:.0%}", "correct on the first message", f"{c['correct']} of {c['n']}"),
        (str(c["wrong"]), "confidently wrong", "on the doctor's labels"),
        (f"{c['asks']}", "asked a question", "the 5 vague cases + 1"),
        (f"{c['after'] / c['n']:.0%}", "correct after one answer", "simulated patient"),
        (f"{statistics.median(ms) / 1000:.1f} s", "median wait", "real portal, GPT-6 Luna")])}
<div class="cols">
<div><h2>Ground truth reviewed by a doctor</h2>
{bullets([
    "Every core50 case <b>reviewed and signed by a physician</b> (Dr. Ravi Patil, MBBS MD General Medicine; 23 Nov 2026): speciality, accepted alternatives, critical details, vague and emergency flags.",
    "36 cases OK as written; 1 label changed (sleeve gastrectomy → Plastic &amp; Reconstructive Surgery); 5 accepted alternatives added; all vague and emergency cases confirmed.",
    "Rescoring every earlier run on the doctor's labels changed no score: the draft labels held up.",
])}</div>
<div><h2>By kind of case</h2>
{table(["Case type", "n", "Correct", "Wrong", "Asks"], [[t, d["n"], d["correct"], d["wrong"], d["asks"]] for t, d in sorted(by.items(), key=lambda kv: -kv[1]["n"])], ["40%", "12%", "16%", "16%", "16%"], "small")}
</div></div>"""
    return page("Step 1 on the doctor-reviewed ground truth", body, "4 · Evaluation · Step 1",
                f"data/evaluation/step1_gold_core50.csv (reviewed) · portal run {run.name}")


def p_step1_sets():
    run = doctor_run()
    core = first_answer(run_rows(run), gold_ok("core50"), "core50")
    med = first_answer(run_rows(REGRESSION_RUN), gold_ok("mediroute"), "mediroute")
    pc = lambda c, k: 100 * c[k] / c["n"]  # noqa: E731
    rows = [("core50 (doctor-reviewed), 50", pc(core, "correct"), pc(core, "wrong"), pc(core, "asks")),
            ("mediroute (lay language), 84", pc(med, "correct"), pc(med, "wrong"), pc(med, "asks")),
            ("unseen, English, 77", 84, 1, 14),
            ("unseen incl. Hinglish (out of scope), 110", 73, 1, 26)]
    chart = stacked_chart(rows, "Step 1 through the real portal: first message", highlight={rows[0][0], rows[2][0]})
    body = f"""{chart}
<div class="cols">
<div><h2>Unseen data: no sign of over-fitting</h2>{bullets([
    "110 brand-new messages, written by a model MediRoute does not use, labels fixed by construction.",
    "English: <b>84%</b> correct on the first message (tuned set: 85%), <b>1%</b> confidently wrong, <b>96%</b> correct after one answer.",
    "A stronger or pricier judge (Gemini 4 Carbon, GPT-6.1 Terra) gave no gain (±3 points) at 3–6× the cost: reverted.",
])}</div>
<div><h2>Where it still asks</h2>{bullets([
    "Very colloquial or Hinglish wording that the medical lookup cannot match: the judge must cite a lookup line, so it asks instead of guessing.",
    "Translation is out of scope, so Hinglish is excluded from the target.",
])}</div></div>"""
    return page("Step 1: real portal and unseen data", body, "4 · Evaluation · Step 1",
                f"portal runs {run.name} (core50) and {REGRESSION_RUN.name} (mediroute); unseen set: team report 7b")


def p_step2():
    left = bar_chart([("Portal end to end", 0.67, True, (0.60, 0.74)), ("Engine, given the speciality", 0.66, False, (0.59, 0.73)),
                      ("Random among eligible", 0.54, False, (0.47, 0.60))], "P@5 (precision): share of the 5 shown that are good")
    right = bar_chart([("Portal end to end", 0.68, True, (0.60, 0.76)), ("Engine, given the speciality", 0.66, False, (0.59, 0.74)),
                       ("Random among eligible", 0.54, False, (0.47, 0.61))], "NDCG@5: good hospitals near the top")
    body = f"""<div class="cols">{left}{right}</div>
{table(["System (first run, website grades)", "NDCG@5", "Capable@3", "Bad@3"], [
    ["<b>Our engine: filter + similarity + bonuses</b>", "<b>0.71</b>", "<b>91%</b>", "<b>0%</b>"],
    ["Keyword search, no filters (search-engine-like)", "0.50", "87%", "51%"],
    ["Random among eligible", "0.61", "84%", "8%"],
    ["LLM capability judge (v2 trial)", "0.66", "87%", "2%"],
    ["+ full website speciality list (12 Nov fix)", "0.81 (p = 0.002)", "93%", "–"],
], ["52%", "16%", "16%", "16%"], "small")}
{bullets([
    "End to end (45 requests, graded from the official NABH scope): <b>P@5 0.67 and NDCG@5 0.68 vs 0.54 random (p &lt; 0.001)</b>, and as good as the engine handed the right speciality (p = 0.56): Step 1 does not lose quality.",
    "Weak spot: rare specialities (P@5 0.43) because our hospital lists miss departments NABH confirms; fix path: fill them from the NABH scopes.",
])}"""
    return page("Step 2: hospital ranking, precision and NDCG", body, "4 · Evaluation · Step 2",
                "Team report sections 8 and 8d; bootstrap 95% CI shown as whiskers")


def p_general_ai():
    chart = paired_chart([("Correct speciality (100 requests)", 89, 85), ("Confidently wrong speciality (lower is better)", 7, 3),
                          ("Hospitals we can verify (NABH/JCI/website)", 62, 100), ("Named hospitals that can treat the need", 76, 86),
                          ("A capable hospital in the top 3", 78, 93)],
                         "Same requests, general AI vs MediRoute", "General AI (Gemini 4 Carbon)", "MediRoute")
    body = f"""{chart}
<div class="cols">
<div><h2>What it shows</h2>{bullets([
    "<b>Speciality: level.</b> A strong chatbot is as good at naming the speciality (89% vs 85%, not significant); 6 of its 7 misses send the patient to emergency care.",
    "<b>Hospitals: the clear difference is verifiability.</b> 38% of the hospitals the chatbot names cannot be checked against any accreditation list; every MediRoute hospital is verified and comes with its reasons.",
])}</div>
<div><h2>Cost</h2>{table(["", "General AI", "MediRoute"], [["LLM cost per request", "$0.0028", "<b>$0.00042</b>"], ["Per 1,000 requests", "$2.83", "<b>$0.42</b>"], ["Model", "large", "small + local search"]], ["40%", "30%", "30%"], "small")}
<p class="muted">We do not claim better speciality accuracy than a strong general AI; the value is grounded, verifiable hospitals at 1/7 of the cost.</p></div></div>"""
    return page("Compared with a general AI", body, "4 · Evaluation", "Team report section 9 (scored with the same test sets and grades)")


def p_safety():
    body = f"""<div class="cols">
<div><h2>Guardrails tested</h2>
{table(["Test", "Result"], [
    ["30-case safety set: crisis (misspelt, Hinglish), red flags, prompt injection, off-topic", "<b>30 of 30</b> as expected (after one fix)"],
    ["Emergency red flags on every gold message (false alarms)", "no false alarm in core50, mediroute or unseen"],
    ["Report about another problem than the typed text (25 cases)", "<b>25 of 25</b>: typed text decides, patient told"],
    ["Critical details kept from 23 PDF reports (85 details)", "93% kept, 94% of decisive ones, 0 invented"],
    ["Regression after each safety change (134 portal messages)", "0 → 1 confidently wrong (run-to-run noise, traced)"],
], ["62%", "38%"], "small")}</div>
<div><h2>Design rules</h2>{bullets([
    "Emergencies are decided by <b>fixed rules, never by the AI</b>; acute suicidal intent → Emergency Medicine + Tele-MANAS 14416 helpline.",
    "The AI can add a crisis message, never remove one.",
    "Personal details (phone, e-mail, IDs) removed before anything is sent or logged; only synthetic data in the demo.",
    "Open: typed prompt injection passed 1 of 2 runs (only affects the user's own result); voter-prompt hardening planned with its own regression.",
])}</div></div>"""
    return page("Safety and robustness", body, "4 · Evaluation", "data/evaluation/step1_safety_set.csv, step1_report_mismatch_set.csv; tests/ (218 automated tests)")


def p_deployment():
    flow = row_of([
        box("GitHub Actions", "CI on every push: code compiles, JS syntax, metrics tests, Docker builds; 218 pytest tests run before each PR", "code"),
        box("Amazon ECR", "API and frontend images, published automatically after CI passes on main", "code"),
        box("ECS Fargate (Sydney)", "one task: Nginx (HTTPS) + FastAPI / LangGraph API + frontend", "ml"),
        box("DuckDNS + TLS", "mediroute-demo.duckdns.org", "out"),
    ])
    body = f"""{flow}
<div class="cols">
<div><h2>How it runs</h2>{bullets([
    "One Fargate task in Sydney (ap-southeast-2) runs Nginx (HTTPS), the FastAPI / LangGraph API and the frontend together; no VM or load balancer to manage.",
    "The LLM is called through OpenRouter (GPT-6 Luna); the MiniLM embedding models run inside the container on CPU (downloaded at start-up), so search needs no external service.",
    "Starting a new ECS task is a deliberate manual step (auto-deploy off); the OpenRouter key is an ECS secret from AWS Parameter Store.",
    "Demo uses synthetic data only; accounts live in task-local SQLite and reset when the task is replaced.",
])}</div>
<div><h2>Observability</h2>{bullets([
    "<b>CloudWatch</b> embedded metrics (EMF): 14 series in namespace MediRoute/Demo: queries, failures, rejections, retries, query time, LLM calls, LLM cost (USD), tokens, LLM latency, API and app health probes.",
    "Dashboard <b>MediRoute</b> (next page): API performance and LLM statistics, plus a live status widget (Lambda).",
    "Per-request trace (prompts, votes, judge, decision, timings) on the admin page.",
])}</div></div>"""
    return page("Deployment on AWS", body, "5 · Deployment", "infra/, .github/workflows/, monitoring/, docs/deployment/")


def p_cloudwatch():
    shot = image(ASSETS / "cloudwatch_dashboard.png", "CloudWatch dashboard",
                 "Add a screenshot of the CloudWatch “MediRoute” dashboard here", "shot wide")
    body = f"""{shot}
{bullets([
    "<b>API performance</b>: queries, average and p95 latency, server failures, browser retries and HTTP 4xx, per day.",
    "<b>LLM statistics</b>: calls, call time, input and output tokens and the provider-reported cost in USD.",
    "Snapshot of one day of demo traffic (a handful of queries), so the latency figures here are a small sample; the measured benchmark latency is on the next page.",
])}"""
    return page("Monitoring: live CloudWatch dashboard", body, "5 · Deployment", "CloudWatch dashboard “MediRoute” (screenshot), monitoring/")


def p_latency():
    body = f"""
{tiles([("2.6 s", "typical wait (p50)", "browser → result"), ("6.5 s", "p95", "judge cases ~5 s"), ("34 ms", "Step 2", "filter + FAISS + rerank, no LLM"),
        ("$0.0004", "per request", "GPT-6 Luna, OpenRouter")])}
{table(["Measure", "p50", "p95", "Note"], [
    ["End to end, all requests", "2.55 s", "6.5 s", "max 8.3 s"],
    ["… both voters agree (65%)", "2.2 s", "4.5 s", "no judge call"],
    ["… judge decided (23%)", "5.1 s", "7.1 s", "2 extra LLM calls in parallel"],
    ["One LLM call", "1.9 s", "3.6 s", "evidence and voter run in parallel"],
    ["Step 2", "34 ms", "53 ms", "no LLM"],
], ["40%", "15%", "15%", "30%"], "small")}
{bullets(["Most of the wait is the LLM; hidden “reasoning” was switched off (it was ~95% of the output).",
          "A local model (llama3.2 on a laptop CPU) is free but p95 ≈ 67 s; kept as an offline option."])}"""
    return page("Latency and cost", body, "5 · Deployment", "Portal test, 100 requests (team report section 10)")


def p_limits():
    body = f"""<div class="cols">
<div><h2>Limitations</h2>{bullets([
    "Ground truth: core50 is doctor-reviewed by <b>one</b> physician; the other test sets and the 1,381 mapping rules are team drafts.",
    "200 hospitals; speciality lists miss departments the NABH scope confirms (rare specialities P@5 0.43).",
    "English only, text PDFs only (no OCR); Hinglish often ends in a question.",
    "No costs, doctor profiles, availability or booking.",
])}</div>
<div><h2>Next steps</h2>{bullets([
    "Fill hospital speciality lists from the NABH scopes, checked by a person.",
    "Doctor review of the remaining sets and the last page of the speciality list; route suicidal thoughts straight to Psychiatry (doctor's comment on C047).",
    "Voter-prompt hardening against typed injection, with a regression run.",
    "Admin page login and an alert rule on the CloudWatch dashboard.",
])}</div></div>
<p class="note"><b>Takeaway:</b> a narrow, two-step design where AI does what it measurably improves, code checks every AI output, and every claim is benchmarked against baselines and a doctor-reviewed ground truth.</p>"""
    return page("Limitations and next steps", body, "6 · Wrap-up")


CSS = """
@page { size: A4 landscape; margin: 0; }
* { box-sizing: border-box; }
body { margin: 0; font-family: "Segoe UI", Arial, sans-serif; color: #1d1d1b; font-size: 12.5pt; }
.slide { width: 297mm; height: 210mm; padding: 13mm 16mm 12mm; page-break-after: always; position: relative; overflow: hidden; }
.kicker { font-size: 9.5pt; letter-spacing: .06em; text-transform: uppercase; color: #2a78d6; font-weight: 600; }
h1 { font-size: 23pt; margin: 2mm 0 5mm; color: #14213d; border-bottom: 2px solid #2a78d6; padding-bottom: 2mm; }
h2 { font-size: 13pt; margin: 3mm 0 2mm; color: #14213d; }
ul { margin: 1mm 0 2mm; padding-left: 5mm; } li { margin: 1.2mm 0; line-height: 1.35; }
table { width: 100%; border-collapse: collapse; margin: 2mm 0; table-layout: fixed; }
th { text-align: left; background: #eef2f8; padding: 1.6mm 2mm; font-size: 10.5pt; }
td { border-bottom: 1px solid #e6e4dc; padding: 1.5mm 2mm; vertical-align: top; font-size: 10.5pt; line-height: 1.3; }
table.small td, table.small th { font-size: 9.6pt; }
.cols { display: grid; grid-template-columns: 1fr 1fr; gap: 8mm; }
.cols.wide-left { grid-template-columns: 1.45fr 1fr; } .cols.wide-right { grid-template-columns: 1fr 1.25fr; }
.muted { color: #6b6a64; font-size: 10.5pt; }
.note { background: #f3f6fb; border-left: 4px solid #2a78d6; padding: 2.5mm 4mm; margin-top: 3mm; }
.source { position: absolute; bottom: 6mm; left: 16mm; right: 16mm; font-size: 8.5pt; color: #8a897f; }
.tiles { display: flex; gap: 4mm; margin: 2mm 0 4mm; }
.tile { flex: 1; border: 1px solid #dfe5ee; border-radius: 3mm; padding: 3mm 4mm; background: #fafbfd; }
.tile b { display: block; font-size: 22pt; color: #2a78d6; } .tile span { display: block; font-weight: 600; font-size: 10.5pt; }
.tile small { color: #6b6a64; font-size: 9pt; }
.flow { display: flex; align-items: stretch; gap: 2mm; margin: 1.5mm 0; }
.arrow { align-self: center; color: #8a897f; font-size: 15pt; }
.box { flex: 1; border-radius: 2.5mm; padding: 2.2mm 3mm; border: 1.5px solid; font-size: 10pt; line-height: 1.3; }
.box b { display: block; font-size: 11pt; margin-bottom: .8mm; } .box span { color: #3d3c38; }
.box.ai { background: #f0edfb; border-color: #7a6bd6; } .box.ml { background: #eaf2fc; border-color: #2a78d6; }
.box.code { background: #eaf5ee; border-color: #3f8a60; } .box.out { background: #fff4e5; border-color: #d39a3a; }
.stage { border: 1.5px dashed #c9c7bf; border-radius: 3mm; padding: 2mm 3mm; margin: 2mm 0; }
.stage-title { font-weight: 700; font-size: 10.5pt; color: #14213d; margin-bottom: 1mm; }
.legend { font-size: 10pt; color: #6b6a64; margin-bottom: 1mm; }
.sw { display: inline-block; width: 11px; height: 11px; border-radius: 2px; border: 1.5px solid; margin: 0 1mm 0 4mm; vertical-align: -1px; }
.sw.ai { background: #f0edfb; border-color: #7a6bd6; } .sw.ml { background: #eaf2fc; border-color: #2a78d6; }
.sw.code { background: #eaf5ee; border-color: #3f8a60; } .sw.out { background: #fff4e5; border-color: #d39a3a; }
.shot { width: 100%; border: 1px solid #dfe5ee; border-radius: 2mm; max-height: 112mm; object-fit: contain; object-position: top; }
.shot.small { max-height: 150mm; }
.shot.wide { max-height: 125mm; }
.placeholder { border: 2px dashed #c9c7bf; border-radius: 3mm; padding: 14mm 6mm; text-align: center; color: #8a897f; font-size: 11pt; }
.title { display: flex; flex-direction: column; justify-content: center; padding: 25mm 25mm; background: linear-gradient(135deg, #f3f7fd 0%, #ffffff 70%); }
.title .big { font-size: 46pt; border: none; margin: 4mm 0 2mm; }
.title .tag { font-size: 17pt; color: #33423f; max-width: 210mm; }
.title .team { font-size: 13pt; margin-top: 10mm; }
.title .disclaimer { margin-top: 12mm; font-size: 10pt; color: #6b6a64; max-width: 200mm; }
svg { display: block; margin: 1mm 0 2mm; }
"""


def build_html() -> str:
    pages = [p_title(), p_idea(), p_use_case(), p_architecture(), p_ai_use(), p_data(), p_eval_design(),
             p_step1_evolution(), p_doctor(), p_step1_sets(), p_step2(), p_general_ai(), p_safety(),
             p_deployment(), p_cloudwatch(), p_latency(), p_limits()]
    return f'<!doctype html><html><head><meta charset="utf-8"><title>MediRoute final report</title><style>{CSS}</style></head><body>{"".join(pages)}</body></html>'


def screenshot_patient_form(pw) -> None:
    """Patient form from the local portal (scripts/serve_frontend.py on port 5500), if it is running."""
    target = ASSETS / "patient_form.png"
    if target.exists():
        return
    browser = pw.chromium.launch()
    try:
        pg = browser.new_page(viewport={"width": 1100, "height": 1300})
        pg.goto("http://127.0.0.1:5500/patient.html", wait_until="networkidle", timeout=15000)
        pg.screenshot(path=str(target))
    except Exception as exc:  # portal not running: the page shows a placeholder instead
        print(f"patient form screenshot skipped: {exc.__class__.__name__}")
    finally:
        browser.close()


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright
    html_path, pdf_path = OUT_DIR / "MediRoute_final_report.html", OUT_DIR / "MediRoute_final_report.pdf"
    with sync_playwright() as pw:
        screenshot_patient_form(pw)
        html_path.write_text(build_html(), encoding="utf-8")
        browser = pw.chromium.launch()
        pg = browser.new_page()
        pg.goto(html_path.resolve().as_uri(), wait_until="load")
        pg.pdf(path=str(pdf_path), width="297mm", height="210mm", print_background=True,
               margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
        browser.close()
    print(f"Wrote {pdf_path}")


if __name__ == "__main__":
    main()
