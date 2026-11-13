"""MediRoute team report (PDF): use case, architecture, Step 1 and Step 2 step by step, data, how the
design evolved, benchmarks, comparison with a general AI, latency and cost, setup and API keys.

    PYTHONPATH=src python scripts/build_team_report_pdf.py

Writes docs/report/MediRoute_team_report.html and .pdf. Numbers are from the runs named under each
table; the general-AI section reads the newest data/evaluation/general_ai/<run>/summary.json, so
rerunning this script after a new run refreshes it.
"""
from __future__ import annotations

import json
from datetime import date
from html import escape as e
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "report"
GENERAL_AI = ROOT / "data" / "evaluation" / "general_ai"
CHART = ROOT / "docs" / "evaluation" / "step1_benchmark_chart.png"


def table(headers, rows, widths=None, cls=""):
    cols = "".join(f'<col style="width:{w}">' for w in widths) if widths else ""
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f'<table class="{cls}"><colgroup>{cols}</colgroup><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def bullets(items):
    return "<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>"


def where(code="", data="", run=""):
    parts = []
    if code:
        parts.append(f"<b>Code</b> {code}")
    if data:
        parts.append(f"<b>Data</b> {data}")
    if run:
        parts.append(f"<b>Rerun</b> <code>{run}</code>")
    return '<div class="where">' + " &nbsp;·&nbsp; ".join(parts) + "</div>"


def flow(boxes, kinds=None):
    """A left-to-right flow of boxes; kinds: 'ai' | 'code' | 'data' | 'out' per box."""
    kinds = kinds or ["code"] * len(boxes)
    cells = []
    for i, (title, sub) in enumerate(boxes):
        cells.append(f'<div class="box {kinds[i]}"><b>{title}</b><span>{sub}</span></div>')
        if i < len(boxes) - 1:
            cells.append('<div class="arrow">→</div>')
    return '<div class="flow">' + "".join(cells) + "</div>"


def pct(x):
    return "–" if x is None else f"{x * 100:.0f}%"


# --------------------------------------------------------------------------------------------- sections
def s_summary():
    tiles = [("85%", "correct speciality", "100 real portal requests"),
             ("3%", "confidently wrong", "otherwise it asks (12%)"),
             ("2.6 s", "typical wait", "p95 6.5 s, GPT-6 Luna"),
             ("0.81", "hospital ranking NDCG@5", "website-checked grades"),
             ("$0.0004", "per request", "OpenRouter")]
    t = "".join(f'<div class="tile"><b>{a}</b><span>{b}</span><small>{c}</small></div>' for a, b, c in tiles)
    return f"""
<h1>MediRoute</h1>
<p class="subtitle">Use case, design and evaluation · team report · {date.today():%d %b %Y}</p>
<div class="tiles">{t}</div>
<h2>In one page</h2>
{bullets([
    "<b>What it does:</b> a patient describes the problem in their own words; MediRoute suggests <b>which speciality to search</b> (Step 1) and lists <b>verified hospitals</b> for it in the chosen area, with the reasons (Step 2).",
    "<b>What it does not do:</b> no diagnosis, no treatment advice, no booking. Procedures are used only when the patient wrote them.",
    "<b>How AI is used:</b> an LLM extracts the evidence and votes; a guarded LLM judge settles disagreements. Code checks every AI output (closed lists, quotes must be in the text) and asks the patient when unsure.",
    "<b>Measured:</b> every design change was benchmarked against baselines (keyword search, meaning search, LLM only, voting). Where AI did not beat simple rules (Step 2 capability matching), we did not use it.",
    "<b>Open:</b> test labels and mapping rules await doctor review; hospital procedure lists are unverified; 201 hospitals only. Work after 11 Nov is local and not yet committed.",
])}
"""


def s_use_case():
    return f"""
<h1>1 · Use case</h1>
{flow([("Patient", "describes the need, city, optional PDF report"),
       ("Step 1", "suggested speciality to search + evidence"),
       ("Step 2", "verified hospitals in the area + reasons"),
       ("Patient", "contacts the hospital; a doctor decides")], ["data", "ai", "code", "out"])}
<h2>Who and why</h2>
{bullets([
    "Patients (including international patients) looking for treatment in India who do not know which department to approach.",
    "Problem: symptoms and lay words do not map obviously to a speciality, and hospital information online is unverified and often commercial.",
    "MediRoute narrows the search: one speciality to search, then hospitals whose speciality is confirmed on their own website, NABH / JCI accreditation shown.",
])}
<h2>Design rules</h2>
{bullets([
    "<b>Discovery, not advice:</b> “Suggested speciality to search”, never a diagnosis; a disclaimer on every result.",
    "<b>Ask when unsure:</b> a short question beats a confident wrong answer; the patient's answer is used in the decision.",
    "<b>Explain every result:</b> the evidence words for the speciality and the ranking reasons for each hospital.",
    "<b>Emergency words</b> (chest pain with breathlessness, suicidal intent…) show an emergency notice first; routing continues.",
    "<b>Fix data at the root:</b> no one-off override rows for single cases.",
])}
<h2>Why a portal and not a chatbot</h2>
{bullets([
    "Answers come only from a fixed, checked hospital list (no invented hospitals or departments).",
    "Every request is logged step by step (admin page), so any answer can be audited.",
    "Every stage is measured on test sets; section 9 compares a general AI on the same questions.",
])}
"""


def s_architecture():
    diagram = ROOT / "docs" / "architecture" / "mediroute_pipeline_architecture.png"
    img = (f'<img src="{diagram.as_uri()}" style="display:block;height:248mm;margin:0 auto">' if diagram.exists() else "")
    return f"""
<h1>2 · Architecture</h1>
{img}
</section><section>
<h1>2 · Architecture (system parts)</h1>
{flow([("Browser", "patient.html · results.html · admin.html (static, port 5500)"),
       ("FastAPI backend", "POST /api/patient-routing (port 8000)"),
       ("Workflow", "parse reports → Step 1 → Step 2 → finalize"),
       ("Result", "speciality + hospitals, stored in the browser session")], ["data", "code", "code", "out"])}
{flow([("Step 1", "specialty_routing/step1"), ("LLM provider", "OpenRouter GPT-6 Luna, or local Ollama, or none"),
       ("Step 2", "hospital_recommendation (engine)"), ("Trace", "logs/step1_trace.jsonl → admin page")],
      ["ai", "ai", "code", "data"])}
<h2>Key choices</h2>
{bullets([
    "<b>Two separate steps:</b> Step 1 decides the speciality; Step 2 only ranks hospitals for it. Each is tested on its own.",
    "<b>One data folder:</b> everything the app reads is in <code>data/processed/</code> and can be rebuilt (section 5).",
    "<b>Provider switch:</b> the same code runs with a hosted LLM (fast), a local LLM (private, slow on CPU) or no LLM (search only).",
    "<b>Everything logged:</b> input (redacted), LLM prompts and answers, votes, the judge, the decision and timings.",
])}
{table(["Part", "Folder / file"], [
    ["Frontend pages and scripts", "<code>frontend/</code> (patient, results, hospital, admin; css, js)"],
    ["API and workflow", "<code>src/mediroute/backend/</code> (workflow/api.py, routing_nodes.py, admin/)"],
    ["Step 1 pipeline", "<code>src/mediroute/specialty_routing/step1/</code> (pipeline, evidence, voters, judge, lookup, safety)"],
    ["Step 2 engine", "<code>src/mediroute/hospital_recommendation/</code> (engine, specialty_filter, retrieval, ranking)"],
    ["Shared lists and rules", "<code>src/mediroute/common/</code> (specialties.py, locations.py)"],
    ["Data builders", "<code>src/mediroute/data_generator/</code> (rebuild.py and the builders)"],
    ["Benchmarks", "<code>scripts/</code> benchmark_step1*.py, portal_benchmark.py, eval_step2.py, compare_general_ai.py"],
], ["35%", "65%"])}
"""


def s_step1():
    S1 = "specialty_routing/step1/"
    steps = [
        ["0 Input", "Message + text of readable reports + earlier answers, joined: message, “Report: …”, “Body area: …”",
         "code", "Reports: text-based PDFs only (no OCR); English only (no translation)", S1 + "pipeline.py · compose_text()"],
        ["1 Protect", "Remove phone numbers, e-mails, ID numbers", "code", "Clinical numbers (L4-L5, eGFR 8) kept",
         S1 + "protect.py · redact()"],
        ["2 Emergency check", "Fixed red-flag rules (crushing chest pain, stroke signs, suicidal words…)", "code",
         "Notice shown first; routing continues", S1 + "safety.py · check_emergency()"],
        ["3a Extract evidence", "LLM copies conditions, procedures, body parts from the text", "LLM",
         "Prompt asks to copy, not interpret", S1 + "evidence.py · EvidenceExtractor.extract()"],
        ["3b Check evidence", "Keep a phrase only if it is really in the text (small typos allowed); drop generic words",
         "code", "Invented phrases are dropped; no evidence → ask", S1 + "evidence.py · verify_phrase(), is_generic()"],
        ["3c Keyword matches", "Add known patient wording from the lay-term list (e.g. “kidney stones”)", "code",
         "Works with no LLM too", S1 + "evidence.py · keyword_matches()"],
        ["4a Lookup voter", "Search each phrase in 10,884 ICD-10 / CCSR / CGHS / lay-term entries by keyword (TF-IDF) and "
         "meaning (MiniLM); fuse the two rankings; best match per phrase; symptom-type matches count half", "ML search",
         "Only names from the 26-speciality list", S1 + "voters.py · HybridLookupVoter · lookup.py · LookupIndex"],
        ["4b LLM voter", "LLM picks 1 of 26 specialities (or “unclear”) using each one's “route here when / not here” rules",
         "LLM", "Closed list; runs in parallel with 4a", S1 + "voters.py · LLMVoter · routes.py · prompts/specialty_v2.txt"],
        ["5 Decide", "Apply the decision rules below, in order", "code", "General Medicine asks once before it is accepted",
         S1 + "pipeline.py · Step1Pipeline.analyze()"],
        ["5b Patient's answer", "Body-area answer that fits only one of the two disputed specialities decides", "code",
         "Never adds a speciality the voters did not suggest", S1 + "pipeline.py · _answer_decides()"],
        ["6 LLM judge", "Chooses between the two candidates, citing evidence lines built by code", "LLM + code",
         "Closed choice · cited lines must exist and support it · quote must be in the text · asked twice in swapped order; "
         "any failure → ask", S1 + "judge.py · LLMJudge.judge(), check()"],
        ["7 Ask", "One short form (questions already answered never repeated); still open → short list of 2–4 with "
         "descriptions + “Something else…”", "code", "No pre-selection in the list",
         S1 + "pipeline.py · _ask_or_offer_choice(), _open_fields(), _shortlist()"],
        ["8 Output + trace", "“Suggested speciality to search: X”, evidence, disclaimer; every stage logged", "code",
         "Admin page reads the trace", S1 + "pipeline.py · _respond() · trace.py · Step1Trace"],
    ]
    rules = [
        ["a", "Lookup and LLM give the same speciality", "Answer (“agreement”)"],
        ["b", "They disagree; the patient's body-area answer fits only one of the two", "Answer (“patient answer”)"],
        ["c", "They disagree otherwise", "LLM judge (stage 6): answer (“judge”) or ask"],
        ["d", "LLM says “unclear”; the lookup's pick fits the patient's body-area answer", "Answer (“patient answer”)"],
        ["e", "LLM says “unclear”", "Ask (“message too general”)"],
        ["f", "LLM unavailable (error, no key, provider “none”); the lookup has a pick", "Answer with a notice (“lookup only”)"],
        ["g", "Nothing usable", "Ask"],
        ["+", "Any answer = General Medicine on the first round", "Ask once, then accept"],
    ]
    models = [["3a evidence, 4b voter", "GPT-6 Luna via OpenRouter (same client); local llama3.2 or none as options",
               "MEDIROUTE_LLM_PROVIDER, MEDIROUTE_OPENROUTER_MODEL"],
              ["4a lookup", "No LLM: TF-IDF + all-MiniLM-L6-v2 embeddings (local)", "fixed"],
              ["6 judge", "GPT-6 Luna, its own client (disagreements only)", "MEDIROUTE_JUDGE_MODEL"]]
    return f"""
<h1>3 · Step 1: patient words → speciality to search</h1>
{flow([("Patient text", "+ report, answers"), ("Evidence", "LLM, checked by code"), ("Lookup voter", "keyword + meaning"),
       ("LLM voter", "1 of 26"), ("Decide", "agree / answer / judge / ask")], ["data", "ai", "code", "ai", "code"])}
{table(["Stage", "What happens", "By", "Guardrail", "Code (src/mediroute/)"], steps, ["12%", "33%", "8%", "22%", "25%"], "small")}
</section><section>
<h1>3 · Step 1: decision rules, models and examples</h1>
<h2>Decision rules (stage 5, first that applies)</h2>
{table(["", "Situation", "Result"], rules, ["5%", "60%", "35%"])}
<h2>Models</h2>
{table(["Stage", "Model", "Setting"], models, ["22%", "50%", "28%"])}
<h2>Why changing the judge model did not change the results</h2>
{bullets([
    "The judge is only called when the two voters disagree: about 20% of requests. The other ~80% never reach it.",
    "Its guards require an evidence line from the medical lookup. When the lookup has no matching line (very colloquial "
    "wording), even a perfect judge cannot confirm the answer, so the app asks. The bottleneck is the evidence, not the judge.",
    "Measured on 77 unseen English messages: GPT-6 Luna 84% / Gemini 4 Carbon 83% / GPT-6.1 Terra 81% first-answer correct; "
    "within 1–3 messages of each other (noise). Luna is kept: same accuracy, 3–6× cheaper, faster (section 7b).",
])}
<h2>Worked examples (real portal requests)</h2>
{bullets([
    "<b>“I have kidney stones and severe pain in my lower back… Mumbai”</b>: evidence “kidney stones”, “severe pain”, “lower back”; lookup Urology, LLM Urology → <b>rule a: Urology</b> (2.2 s).",
    "<b>“I am having sciatic nerve pain since 3 months”</b>: lookup Neurology (“Lesion of sciatic nerve”), LLM Orthopaedics (“Sciatica”); rule c → the judge says unclear → one question; answer “Bones, joints and muscles” fits Orthopaedics only → <b>rule b: Orthopaedics</b>.",
])}
{where("specialty_routing/step1/ (all files above)", "data/processed/specialties.csv, specialty_mapping.csv, step1_lookup.csv",
       "python scripts/api_smoke_step1.py")}
</section><section>
<h1>3 · Demo Q&amp;A: why stage 3 (evidence) uses an LLM</h1>
<p><b>Say this:</b> “The evidence step turns a free-form message into checked medical phrases. It raises lookup
accuracy from 87–88% to 93%, keeps the two voters independent, stops guessing on vague messages and shows the
patient why, for about $0.00004 and no extra waiting time.”</p>
{table(["#", "Reason", "Detail / proof"], [
    ["1", "Measured accuracy gain", "Lookup on LLM-extracted phrases 93% vs raw text 87–88% (mediroute set, Step 1 benchmark, section 7)"],
    ["2", "Patients write freely", "“blocked arteries”, “sugar problem”, “heart is weak”: a fixed keyword list only finds words it already has"],
    ["3", "Removes noise before search", "“my mother”, “for months”, “Mumbai”, “my child” would pull wrong matches (“child” → Paediatrics)"],
    ["4", "Keeps the voters independent", "Lookup searches the phrases + medical data; the LLM voter reads the whole text and never sees the lookup. Agreement can be trusted"],
    ["5", "Checked by code, cannot invent", "Kept only if ≥ 60% of its words are in the text; generic words and hidden identifiers dropped; every check is logged"],
    ["6", "Safety gate for vague messages", "No medical phrase (“a good hospital in Pune”) → ask the patient, never guess"],
    ["7", "Explains the answer", "Kept phrases are the evidence chips, always in the patient's own words"],
    ["8", "Helps Step 2", "Procedures (“endoscopy”, “knee replacement”) give the procedure bonus (+0.04 each, max 0.08)"],
    ["9", "Almost free", "Runs at the same time as the LLM voter; ≈ 258 + 35 tokens, ≈ $0.00004; temperature 0, fixed seed"],
    ["10", "Not a single point of failure", "LLM down → code-only keyword matches; the lookup still runs"],
], ["5%", "27%", "68%"], "small")}
<h2>Worked example (real request, 13 Nov 2026, GPT-6 Luna)</h2>
{table(["", "Content"], [
    ["Patient", "“I have acid reflux and stomach pain for months, doctor suggested endoscopy”"],
    ["LLM input", "Fixed instruction (prompts/evidence_v1.txt: copy conditions, procedures, body parts word for word; do not diagnose) + the message"],
    ["LLM output", '{"conditions":["acid reflux","stomach pain"], "procedures":["endoscopy"], "body_parts":["stomach"]}  (2.9 s)'],
    ["Code check", "All 4 phrases found in the text (100%) → kept; keyword matches add “acid reflux”, “endoscopy”"],
    ["To the lookup", "acid reflux · stomach pain · endoscopy → Gastroenterology 0.097 (Urology 0.006, ENT 0.003)"],
    ["Result", "LLM voter also Gastroenterology → agreement; Step 2 gets “endoscopy” as a procedure"],
], ["16%", "84%"], "small")}
<h2>Likely follow-up questions</h2>
{bullets([
    "<b>“Why not keywords only?”</b> That is the no-LLM fallback. It misses wording not in the list, so more patients get a question instead of an answer. Not benchmarked on its own yet (replay test, no API cost).",
    "<b>“The LLM voter already returns evidence_terms; why a second call?”</b> Those are the words the LLM picked to justify its own answer. Feeding them to the lookup would tie the two voters together, so a shared mistake would look like agreement.",
    "<b>“Does it slow the patient down?”</b> No. It runs in parallel with the LLM voter; the whole of Step 1 takes ≈ 3 s.",
    "<b>“Can it hallucinate?”</b> It can propose a phrase, but code drops any phrase that is not in the patient's text. The admin page shows every phrase as kept or dropped, with the reason.",
    "<b>“Where can I see it?”</b> Admin page → any request → “Step 1: how the speciality was worked out”; diagram: docs/architecture/mediroute_algorithms.png.",
])}
"""


def s_step2():
    steps = [
        ["1 Eligible", "Hospitals whose speciality list includes Step 1's speciality: from the hospital's own website (full list) or the team sheet (marked unverified)"],
        ["2 Area", "The chosen city or search area (cities.csv, e.g. Delhi NCR = New Delhi + Gurugram + Noida), or a state"],
        ["3 Similarity", "FAISS search with multi-qa-MiniLM: the patient's speciality, diagnoses and procedures vs each hospital's services; top 3×k"],
        ["4 Bonuses", "Website-confirmed speciality +0.04 · matching procedure up to +0.08 · verified details +0.03 · NABH +0.02 · JCI +0.02 · international services +0.02 · evidence ≤ +0.03 (cap 0.20); each bonus becomes a reason"],
        ["5 Top 5", "Sorted by similarity + bonus, with the reasons shown on the card"],
        ["6 Outside area", "Fewer than 3 in the area → fill from the same state, then the rest of India, as a separate labelled group after the in-area hospitals"],
    ]
    return f"""
<h1>4 · Step 2: speciality → ranked hospitals</h1>
{flow([("Speciality + area", "from Step 1 and the form"), ("Eligible", "speciality + area filter"), ("Similarity", "FAISS, MiniLM"),
       ("Bonuses", "transparent, ≤ 0.20"), ("Top 5", "+ reasons, outside-area group")], ["data", "code", "ai", "code", "out"])}
{table(["Stage", "What happens"], steps, ["17%", "83%"])}
<h2>Worked example</h2>
{bullets([
    "<b>IVF in Pune:</b> 2 hospitals in Pune list Reproductive Medicine → both shown first; then “Outside your area · Elsewhere in the same state” (Jaslok, Mumbai) and “Elsewhere in India”, with the note “Only 2 hospitals in Pune offer Reproductive Medicine in our data”.",
    "Step 2 uses <b>no LLM at run time</b>: the v2 trial showed an LLM capability judge ranked worse than today's engine (section 8).",
])}
{where("hospital_recommendation/engine.py, specialty_filter.py, ranking/hospital_reranker.py", "data/processed/hospitals.csv, vector_store/",
       "python scripts/api_smoke_workflow.py")}
"""


def s_data():
    rows = [
        ["specialties.csv", "26 specialities, description, “route here when / not here”", "hand-written (doctor review)", "Step 1 + 2"],
        ["specialty_mapping.csv", "1,381 rules “X → speciality”: AHRQ CCSR, CGHS, lay terms, hospital labels, body areas", "CDC / AHRQ / CGHS + team (draft)", "Step 1 + 2"],
        ["step1_lookup.csv", "10,884 searchable entries (ICD-10-CM via CCSR, CGHS procedures, lay terms)", "built: rebuild --step lookup", "Step 1"],
        ["hospitals.csv", "201 hospitals: NABH / JCI / website checks, full website speciality list, team-sheet details", "built: rebuild --step hospitals", "Step 1 + 2"],
        ["cities.csv", "Cities, states, search areas", "hand-written", "Step 2"],
        ["vector_store/", "FAISS index of the hospitals + lookup embeddings", "built: rebuild --step index", "Step 1 + 2"],
    ]
    return f"""
<h1>5 · Data</h1>
{table(["File (data/processed/)", "What it holds", "Source", "Used by"], rows, ["20%", "45%", "22%", "13%"])}
{bullets([
    "Raw inputs in <code>data/raw/</code>, intermediate files in <code>data/interim/</code>, retired data and code in <code>archive/</code>.",
    "Every processed file can be regenerated: <code>python -m mediroute.data_generator.rebuild</code> (or <code>--step mapping|hospitals|lookup|index</code>).",
    "<b>Fix of 12 Nov:</b> the hospital builder kept only the first 6 specialities found on each website. It now keeps the full list (e.g. Dermatology 3 → 49 hospitals, Nephrology 32 → 129); checked against website grades, recall 0.54 → 0.78 at precision 0.94 → 0.90.",
    "All rules are marked <b>draft</b> until the doctor review (docs/review/MediRoute_doctor_review.pdf).",
])}
"""


def s_evolution():
    rows = [
        ["Start", "3 voters (keyword, meaning, local LLM), 2-of-3 majority", "Baseline app", "80% correct · 2% wrong · 18% asks"],
        ["Baselines", "Keyword only / meaning only / LLM only", "TA: evaluation and baselines first", "86% / 92% (73% on lay language) / 76% with 16% wrong"],
        ["Hybrid lookup", "Keyword + meaning merged into one voter; ask on disagreement", "Voters 1 and 2 shared one dataset and outvoted a right LLM", "68% · 30% asks: too many questions"],
        ["Clean data", "AHRQ CCSR mapping, strong / weak lay terms", "Hand-drawn ICD ranges (throat pain → Cardiology)", "66% · 0% wrong: safer, reviewable"],
        ["LLM judge", "Guarded GPT-6 Luna judge on disagreements", "Too many questions", "82% · 16% asks: biggest gain"],
        ["Boundaries", "Each speciality's “route here when / not here” in the prompt", "LLM mixed up neighbouring specialities", "86% · 2% wrong · 12% asks: adopted"],
        ["Portal test", "100 real requests through the app; fixes 1–3 (LLM “unclear” → ask, …)", "Test the real system, not a script", "85% · 3% wrong · 12% asks · 2.6 s"],
        ["Step 2 v2 trial", "Criteria + TOPSIS; capability by rules / embeddings / LLM", "Justify (or not) an LLM in Step 2", "LLM 0.66 vs today 0.71 NDCG@5 → kept today's engine"],
        ["Fair grading", "Score only on grades whose website was read", "49% of grades were fallbacks built from our own data (circular)", "Benchmark can now judge data changes"],
        ["Full speciality list", "Use every speciality found on the website", "Lists were cut at 6; hospitals wrongly filtered out", "NDCG@5 0.73 → 0.81 (p = 0.002)"],
        ["Outside-area group", "Fill with nearest hospitals when < 3 in the area", "Empty or one-hospital pages", "Capable@3 91% → 93%"],
        ["Patient answers count", "Body-area answer decides between the 2 candidates; short list", "Same question asked twice, then all 26 specialities", "Sciatica case: one question → Orthopaedics"],
        ["Unseen-data test", "110 brand-new messages written by a model MediRoute does not use (labels by construction)", "Numbers so far came from cases we had tuned on", "English: 84% first answer, 94% right outcome, 96% after one answer, 1% confidently wrong"],
        ["Stronger judge (tried, reverted)", "F1: boundaries in the judge prompt; F2: Gemini 4 Carbon or GPT-6.1 Terra as judge", "Too many questions on disagreements", "No gain on unseen data (all within ±3%); 3–6× the cost, Gemini ~11 s per call → kept GPT-6 Luna"],
        ["Screens", "Compact form, input vs output, honest ranking text, themes, academic disclaimer", "Scrolling, fake weights, look-alike theme", "Form 1,896 → 1,084 px; hospitals start on screen one"],
    ]
    return f"""
<h1>6 · How the design evolved (11–12 Nov 2026)</h1>
<p class="muted">Chronological; each row is one change and why. Step 1 numbers on the 50 core test cases unless marked; Step 2 numbers on the 45-request test set.</p>
{table(["Stage", "Change", "Why", "Result"], rows, ["14%", "32%", "29%", "25%"], "small")}
"""


def s_bench1():
    grid = [
        ["1", "Keyword search only", "86%", "0.78", "14%", "0%"],
        ["2", "Meaning search only", "92%", "0.84", "8%", "0%"],
        ["3", "LLM only", "76%", "0.77", "16%", "8%"],
        ["4", "3 voters, 2-of-3 majority (old app)", "80%", "0.80", "2%", "18%"],
        ["5", "Hybrid lookup + LLM, ask on disagreement", "68%", "0.82", "2%", "30%"],
        ["6", "<b>5 +</b> clean data (CCSR, strong / weak lay terms)", "66%", "0.81", "0%", "34%"],
        ["7", "<b>5 +</b> clean data + guarded LLM judge", "82%", "0.80", "2%", "16%"],
        ["8", "<b>5 +</b> clean data + LLM judge + speciality boundaries in the prompt (adopted)", "<b>86%</b>", "0.81", "<b>2%</b>", "<b>12%</b>"],
    ]
    portal = [["core50 (team-written)", "50", "88%", "0%", "12%"], ["mediroute (lay language)", "25", "92%", "0%", "8%"],
              ["gretel (synthetic)", "25", "72%", "12%", "16%"], ["<b>All</b>", "100", "<b>85%</b>", "<b>3%</b>", "<b>12%</b>"]]
    img = f'<img src="{CHART.as_uri()}" class="chart">' if CHART.exists() else ""
    return f"""
<h1>7 · Benchmark: Step 1</h1>
<h2>Test sets</h2>
{table(["Set", "What it is", "Sample message → expected speciality"], [
    ["<b>core50</b><br>50 cases, 25 specialities",
     "Team-written cases covering the hard situations on purpose: diagnosis (12), report attached (10), procedure only (8), noisy / misspelled report (5), vague (5), CGHS gaps (4), emergency (3), children (3). 15 cases include report text.",
     "“My father, 67, has severe aortic stenosis and his cardiologist says he needs valve replacement surgery.” → Cardiothoracic Surgery (Cardiology accepted)<br>“Biopsy report attached.” + “HISTOPATHOLOGY: Right breast lump, core biopsy…” → Oncology<br>“pain” → a question is expected"],
    ["<b>mediroute</b><br>84 cases, all 26 specialities",
     "Team-written short patient messages: lay wording (31), named diagnosis (22), clear requests (14), report (7), vague (5), several problems (3), misspellings (2). Tests everyday language.",
     "“I get chest tightness when I climb stairs and it goes away when I rest” → Cardiology<br>“high blood pressure not controlled with 3 medicines, swollen ankles” → Cardiology (Nephrology accepted)"],
    ["<b>gretel</b><br>212 cases, 10 specialities",
     "Public dataset (gretelai/symptom_to_diagnosis, test split, Apache-2.0): longer symptom descriptions written for 22 diagnoses (7–10 each: peptic ulcer, pneumonia, migraine, psoriasis, malaria…), mapped by us to a speciality. Symptom-only, no named condition: the hardest set.",
     "“I have a burning sensation in my stomach that comes and goes. It's worse when I eat and when I lie down…” → Gastroenterology<br>“I've been having headaches and migraines, and I can't sleep…” → General Medicine"],
], ["17%", "41%", "42%"], "small")}
{bullets([
    "Each case has an expected speciality and optional accepted alternatives. All labels are <b>drafts awaiting doctor review</b> (data/evaluation/step1_gold_*.csv).",
    "The design grid uses core50; the portal test uses all of core50 plus an even sample of 25 mediroute and 25 gretel cases (100 requests).",
    "<b>Correct</b> = the expected speciality or an accepted alternative; a question counts as not correct. <b>Confidently wrong</b> = answered and wrong (the costly error). <b>Asks</b> = asked the patient. <b>NDCG@3</b> = the right speciality near the top of the 3 candidates.",
])}
<h2>Design grid (core50, one change per row)</h2>
<p class="muted">Rows 1–3 are single-method baselines; row 4 is the old app. Row 5 restarts from a new base (hybrid lookup + LLM, ask on disagreement), and rows 6–8 are <b>5 +</b> the changes added one at a time.</p>
{table(["#", "Design", "Correct", "NDCG@3", "Confidently wrong", "Asks"], grid, ["5%", "47%", "12%", "12%", "13%", "11%"])}
<h2>Real portal test (100 requests through the running app, GPT-6 Luna)</h2>
{table(["Test set", "n", "Correct", "Confidently wrong", "Asks"], portal, ["40%", "10%", "17%", "18%", "15%"])}
{img}
{where("", "data/evaluation/results/, data/evaluation/portal_runs/20261111_230644",
       "python scripts/portal_benchmark.py --n 100 --spacing 15")}
</section><section>
<h1>7b · Step 1 on unseen data, and a stronger judge (tried and reverted)</h1>
{bullets([
    "<b>Why:</b> the numbers above come from cases we had looked at while tuning. To check they hold, a <b>brand-new set</b> of 110 messages was written by a model MediRoute does not use (Mistral Large 4): for each of the 26 specialities we fixed the speciality and the kind of message first (everyday symptoms, named diagnosis, advised procedure, report snippet), so the expected answer is known by construction; plus 10 vague messages. Labels are drafts.",
    "<b>Measures:</b> <b>first answer</b> (as before); <b>right outcome</b> = correct, or a question on a message that is really vague; <b>after one answer</b> = the simulated patient answers the body-area question once.",
    "<b>Tried:</b> F1 = the judge also sees each candidate's “route here when / not here” rules; F2 = a stronger judge model (Gemini 4 Carbon or GPT-6.1 Terra). The judge is only called on disagreements.",
])}
<h2>English messages (77): the project's scope</h2>
{table(["Judge", "First answer correct", "Confidently wrong", "Asked", "Right outcome", "Correct after 1 answer"], [
    ["<b>Today: GPT-6 Luna</b>", "<b>84%</b>", "<b>1%</b>", "14%", "<b>94%</b>", "<b>96%</b>"],
    ["F1: boundaries in the judge prompt", "82%", "1%", "17%", "91%", "95%"],
    ["F1 + GPT-6.1 Terra", "81%", "3%", "17%", "90%", "95%"],
    ["F1 + Gemini 4 Carbon", "83%", "1%", "16%", "92%", "96%"],
], ["34%", "14%", "13%", "11%", "13%", "15%"])}
<h2>All 110 messages, including 33 in Hinglish (out of scope)</h2>
{table(["Judge", "First answer correct", "Confidently wrong", "Asked", "Right outcome", "Correct after 1 answer"], [
    ["Today: GPT-6 Luna", "73%", "1%", "26%", "79%", "95%"],
    ["F1", "71%", "1%", "28%", "77%", "95%"],
    ["F1 + GPT-6.1 Terra", "70%", "2%", "28%", "76%", "95%"],
    ["F1 + Gemini 4 Carbon", "72%", "1%", "27%", "78%", "95%"],
], ["34%", "14%", "13%", "11%", "13%", "15%"])}
{table(["Judge model", "Cost per judge call", "Time per judge call"], [
    ["GPT-6 Luna (kept)", "≈ $0.0002", "≈ 2 s"], ["GPT-6.1 Terra", "$0.0008", "2.7 s"], ["Gemini 4 Carbon", "$0.0022", "11 s"]],
    ["40%", "30%", "30%"])}
{bullets([
    "<b>Target met on unseen English data with today's design:</b> right outcome 94% (> 90%), confidently wrong 1% (≤ 2%); 96% end on the right speciality after at most one question. First-answer accuracy (84%) matches the tuned set (85%): no sign of over-fitting.",
    "<b>F1 and F2 did not help</b> (all within ±3 points) and cost 3–6× more; Gemini adds ~11 s to the wait. Both were <b>reverted</b>; the app keeps the GPT-6 Luna judge and its original prompt.",
    "<b>Why a better judge cannot help:</b> most questions come from messages the medical lookup cannot match (very colloquial or Hinglish wording). The judge must cite a lookup evidence line, so with no line it cannot confirm the LLM even when the LLM is right. Translation is out of scope, so Hinglish is excluded from the target.",
])}
{where("scripts/benchmark_step1_unseen.py, scripts/make_step1_unseen_set.py", "data/evaluation/step1_gold_unseen.csv, data/evaluation/step1_unseen/",
       "python scripts/benchmark_step1_unseen.py --set new --configs base")}
"""


def s_bench2():
    base = [
        ["Today's engine (filter + FAISS + bonuses)", "0.71", "91%", "0%"],
        ["B0 random among eligible", "0.61", "84%", "8%"],
        ["B1 keyword search, no filters (search-engine-like)", "0.50", "87%", "<b>51%</b>"],
        ["B2 filter, alphabetical", "0.60", "87%", "4%"],
        ["B3 filter + bonuses (no similarity)", "0.68", "91%", "0%"],
        ["B4 filter + similarity (no bonuses)", "0.65", "87%", "2%"],
        ["v2: criteria + TOPSIS, capability by rules", "0.70", "91%", "0%"],
        ["v2: capability by embeddings", "0.67", "89%", "2%"],
        ["v2: capability by LLM judge", "0.66", "87%", "2%"],
    ]
    fixes = [["Before 12 Nov fixes", "0.729", "0.58", "91%", "87%"],
             ["+ full website speciality list", "0.807", "0.68", "95%", "91%"],
             ["+ outside-area group", "0.807", "0.68", "95%", "<b>93%</b>"]]
    return f"""
<h1>8 · Benchmark: Step 2</h1>
{bullets([
    "<b>Test set:</b> 45 requests in 5 groups (big city + speciality, big city + procedure, state / anywhere, small city, edge cases); patient wording differs from hospital wording on purpose.",
    "<b>Grades 0–3</b> per (hospital, need) from the hospital's own website pages, drafted by a different model (GPT-5.6 Luna) with a citation check; a human spot-check of 20% is pending.",
    "<b>Metrics:</b> NDCG@5 (good hospitals near the top), Capable@3 (a capable hospital in the top 3), Bad@3 (a hospital that cannot treat the need in the top 3), paired permutation test.",
])}
<h2>Baselines and the v2 trial (first run, all grades)</h2>
{table(["System", "NDCG@5", "Capable@3", "Bad@3"], base, ["58%", "14%", "14%", "14%"])}
<p class="muted">Direct capability test on 301 checked pairs: rules precision 63% / recall 50% (9 unsafe), embeddings 62 / 57 (13), LLM 58 / 47 (16). The bottleneck is the data (short, unverified procedure lists), not the method.</p>
<h2>12 Nov fixes (scored only on grades whose website was read)</h2>
{table(["Engine", "NDCG@5", "Recall@5", "Hit@3", "Capable@3"], fixes, ["40%", "15%", "15%", "15%", "15%"])}
{bullets([
    "<b>Why “website read only”:</b> 49% of grades were fallbacks for sites that block automated reading, built from our own (then cut-short) speciality list, so they punished the data fix. Standard practice: treat unjudged items as unknown (condensed lists).",
    "The full-list gain is significant (p = 0.002; 16 requests better, 4 worse). Bad@3 rose from 9% to 16%: 7 cases, all “not confirmed on the pages read”, queued for the human check.",
])}
{where("", "data/evaluation/step2_gold.csv, step2_capability_grades.csv, results/20261112_*_step2_judged",
       "python scripts/eval_step2.py run --judged-only")}
"""


def s_ta_benchmarks():
    return f"""
<h1>8c · Benchmarks the TA asked for (mid-sem feedback)</h1>
<p>The mid-sem feedback (verdict “Needs improvements”) said the evaluation plan “needs substantial strengthening” and asked for
specific experiments. This section lists each request, the test we ran and where its result is. The two newest tests (13 Nov 2026)
follow on the next pages, each with <b>why</b> it was done, <b>how</b> and the <b>outcome</b>.</p>
{table(["The TA asked (feedback, quoted)", "Test we ran", "Result", "Where"], [
    ["“Establish keyword-search and speciality-filtering baselines … evaluate ranking using Precision@K, Recall@K, and NDCG@K”",
     "Step 2: 4 baselines + ablations on 45 graded requests; Step 1: keyword, meaning and LLM-only baselines",
     "Step 2 NDCG@5 0.807 vs 0.750 random; keyword search puts an incapable hospital in the top 3 for 51% of requests (ours 0%). Step 1: 86% vs 76% LLM only", "8, 7"],
    ["“Define relevance-labelled test cases”", "Graded hospital labels 0–3 from hospital websites; Step 1 gold sets (core50, mediroute, gretel, unseen)",
     "45 Step 2 requests; 346 + 110 Step 1 messages", "7, 7b, 8"],
    ["“Medical information extraction should be evaluated separately for accuracy and omission of critical details”",
     "<b>Critical-detail metric on 23 PDF reports (85 details, 3 levels)</b>", "<b>93% of details kept, 94% of decisive ones; 0 invented; one loss point found (6,000-character cut)</b>", "<b>8c.1</b>"],
    ["“Assess the effect of different ranking weights … test alternative ranking weights rather than relying on arbitrarily assigned values”",
     "<b>13 weight variants on the Step 2 gold set</b>", "<b>Bonuses help (p = 0.02); exact values do not matter (×0.5 to ×4 within noise)</b>", "<b>8c.2</b>"],
    ["“Incomplete patient queries”", "Vague messages in the unseen set; clarification flow", "Right outcome 94% (answer, or a question when the message is really vague)", "7b"],
    ["“Noisy medical reports”", "8 layout cases: letterhead, lab table, two columns, long report, typos, personal details, two reports", "All read correctly except the long report (cut)", "8c.1"],
    ["“Compare conventional retrieval with the AI-based approach … demonstrate measurable value beyond conventional hospital search”",
     "Same requests through a general AI assistant", "See section 9", "9"],
    ["“Prioritise medical suitability … over geographical convenience”", "Capable@3 with the outside-area group; all-India variant",
     "Capable@3 93%; all-India comparison needs grades outside each area (open, tracker row 50)", "8, 8c.2"],
    ["“Expert-reviewed diagnosis-to-specialisation mappings”", "Doctor review pack prepared", "Pending", "13"],
], ["31%", "27%", "34%", "8%"], "small")}
</section><section>
<h1>8c.1 · Extraction accuracy and omission of critical details (13 Nov 2026)</h1>
<div class="ta"><b>What the TA asked</b> (mid-sem feedback): “Medical information extraction should be evaluated separately for accuracy and omission of critical details.” and “Evaluate extraction errors, unsupported recommendations, and performance on ambiguous cases.” Also: “noisy medical reports”.</div>
<h2>Why this test was done</h2>
{bullets([
    "Every other Step 1 test scores only the <b>final speciality</b>. A report can be routed correctly from one detail while others are missed, and when routing fails we could not say whether the PDF reader, the LLM or our code check lost the information.",
    "The TA asked for extraction to be evaluated <b>separately</b> (accuracy and omissions). Missing a detail such as “CABG advised” or “carcinoma” is also the error that matters most for patients, and the procedures found here feed the Step 2 procedure bonus.",
])}
<h2>How it was done</h2>
{bullets([
    "<b>Data:</b> the 23 readable synthetic PDF reports (15 core reports + 8 layout cases: letterhead, lab table, two columns, long report, typos, personal details, two reports, report with no typed text). Unreadable files (empty, locked, scanned) are tested separately and correctly refused.",
    "<b>Labels:</b> for each report 2–5 <b>critical details</b> (85 in all), tagged diagnosis / finding / procedure / body part; <b>decisive</b> = the details the speciality depends on (e.g. “triple vessel disease”, “CABG”). Drafted from the report texts by the team, <b>pending doctor review</b> (data/evaluation/report_critical_details.csv).",
    "<b>Run:</b> each report goes through the real Step 1 pipeline with the app's model (GPT-6 Luna), as the patient page would send it (typed text + report text, cut at 6,000 characters).",
    "<b>Three levels</b> per detail, so a loss can be located: <b>A</b> in the text read from the PDF (and after the cut) · <b>B</b> returned by the evidence LLM · <b>C</b> kept after the code check, i.e. used by the voters, shown to the patient and passed to Step 2.",
    "<b>Match rule:</b> a detail counts as captured when one extracted phrase covers at least half of its words (abbreviations and close spellings count; text broken by line breaks such as “necro sis” is joined). Every miss was checked by hand.",
])}
<h2>Outcome</h2>
{table(["Level", "All 85 details", "Decisive details"], [
    ["A · in the PDF text", "100%", "100%"],
    ["A · still there after the 6,000-character cut", "96%", "94%"],
    ["B · returned by the evidence LLM", "93%", "94%"],
    ["<b>C · kept and used</b>", "<b>93%</b>", "<b>94%</b>"],
], ["50%", "25%", "25%"])}
{table(["Type", "Details", "Kept"], [["Diagnosis", "28", "96%"], ["Finding", "41", "93%"], ["Procedure", "14", "86%"], ["Body part", "2", "100%"]],
       ["50%", "25%", "25%"], "small")}
{bullets([
    "<b>Only 6 of 85 details were lost.</b> 3 were dropped by the LLM, none of them decisive: FNAC, Ficat stage IV, Bethesda category V. The other 3 were lost to the 6,000-character cut, all in L04.",
    "<b>The one real failure is the long report (L04):</b> its diagnosis and the CABG plan sit at character ~6,560 of a 6,900-character discharge summary, after the cut, so Step 1 asked a question instead of answering. <b>Fix path:</b> keep the end of the report too, or the “impression / diagnosis / plan” sections, instead of only the first 6,000 characters.",
    "<b>Nothing invented:</b> no unsupported phrase reached the voters (the code check dropped the 1 phrase that was not in the text). Layout noise did not hurt: letterhead, lab tables, two columns, typos and personal details were all read correctly.",
    "<b>Extra phrases:</b> 39 kept phrases are not critical details, mostly harmless (test names such as “USG NECK”, lab names such as “Potassium”, body parts). One to watch: in L01 the letterhead's department list put “oncology” and “urology” into the evidence; the answer was still right.",
    "<b>Speciality:</b> 22 of 23 correct (96%); the miss is L04.",
    "<b>Note on the run:</b> a first attempt hit the provider's limit of 20 requests a minute and was discarded; the script now spaces requests and retries, so a rate limit can never be counted as a miss.",
])}
{where("scripts/eval_report_extraction.py", "data/evaluation/report_critical_details.csv, synthetic_reports/, results/20261113_162049_report_extraction",
       "MEDIROUTE_OPENROUTER_MODEL=openai/gpt-6-luna python scripts/eval_report_extraction.py")}
</section><section>
<h1>8c.2 · Alternative ranking weights (13 Nov 2026)</h1>
<div class="ta"><b>What the TA asked</b> (mid-sem feedback): “Experiments should also assess the effect of different ranking weights” and “Test alternative ranking weights rather than relying on arbitrarily assigned values.”</div>
<h2>Why this test was done</h2>
{bullets([
    "Step 2 adds fixed bonuses to the similarity score (website-confirmed speciality +0.04, each matching procedure +0.04 up to 0.08, verified details +0.03, NABH +0.02, JCI +0.02, international services +0.02, evidence quality up to +0.03; total capped at 0.20). These values were set by hand.",
    "The TA asked for <b>alternative ranking weights to be tested</b> rather than chosen arbitrarily. The question: do the bonuses help at all, and would a different choice of values give a better ranking?",
])}
<h2>How it was done</h2>
{bullets([
    "The real Step 2 engine was rerun on the <b>same 45 gold requests and grades</b> as section 8, once per weight variant; only the bonus weights changed. No LLM, no API cost; the app code was not changed.",
    "<b>13 variants:</b> current weights · no bonuses (similarity only) · every bonus ×0.5, ×2, ×4 · each of the 7 bonuses removed on its own (leave-one-out) · current weights searched across all of India (no area filter).",
    "<b>Scoring:</b> NDCG@5 and Capable@3 as in section 8, with a <b>paired permutation test</b> against the current weights. Run twice: on grades whose website was read (as reported in section 8) and on all grades, as a robustness check. The current weights reproduce the reported NDCG@5 of 0.807 exactly.",
])}
<h2>Outcome</h2>
{table(["Variant", "NDCG@5 (website-read grades)", "NDCG@5 (all grades)", "Different from current?"], [
    ["<b>Current weights</b>", "<b>0.807</b>", "<b>0.701</b>", "–"],
    ["No bonuses (similarity only)", "0.776", "0.648", "<b>yes, worse</b> (p = 0.02 / 0.01)"],
    ["All bonuses ×0.5", "0.796", "0.690", "no (p = 0.15 / 0.38)"],
    ["All bonuses ×2", "0.812", "0.695", "no (p = 0.72 / 0.57)"],
    ["All bonuses ×4", "0.821", "0.686", "no (p = 0.30 / 0.31)"],
    ["Without website-confirmed speciality", "0.795", "0.674", "not significant / <b>yes, worse</b> (p = 0.10 / 0.004)"],
    ["Without any one other bonus", "0.801–0.812", "0.694–0.711", "no (all p ≥ 0.06)"],
], ["38%", "20%", "17%", "25%"], "small")}
{bullets([
    "<b>The bonuses matter:</b> similarity alone is significantly worse on both grade sets, and changes the top 5 for 30 of 45 requests.",
    "<b>The exact values do not:</b> halving, doubling or quadrupling every bonus stays within noise. ×4 looked slightly better on one grade set and worse on the other, so it is not a real gain. The ranking is <b>robust to the choice of weights</b>, so we keep the current values rather than tune them on 45 requests (which would overfit).",
    "<b>The bonus that carries most of the effect</b> is the website-confirmed speciality; no other single bonus makes a measurable difference on its own.",
    "<b>All-India search</b> (no area filter) cannot settle “suitability before location” yet: the grades were collected mostly for hospitals inside each request's area, so hospitals elsewhere are largely ungraded. That question needs its own grading round (tracker row 50).",
    "<b>Limits:</b> 45 requests, overlapping confidence intervals, grades drafted by a model with a 20% human check pending.",
])}
{where("scripts/eval_step2_weights.py", "data/evaluation/results/20261113_161008_step2_weights (and _allgrades)",
       "python scripts/eval_step2_weights.py [--all-grades]")}
"""


def s_general_ai():
    runs = sorted(p for p in GENERAL_AI.glob("2*") if (p / "summary.json").exists()) if GENERAL_AI.exists() else []
    if not runs:
        return """<h1>9 · Compared with a general AI</h1><p>Run not finished yet: rerun this script after
<code>python scripts/compare_general_ai.py score</code>.</p>"""
    s = json.loads((runs[-1] / "summary.json").read_text(encoding="utf-8"))
    a, b = s["step1"], s["step2"]
    rows1 = [["Correct speciality", pct(a["correct"]), pct(a["mediroute"]["correct"])],
             ["Confidently wrong", f'{pct(a["confidently_wrong"])} (of which {pct(a.get("wrong_but_emergency"))} “go to emergency”)',
              pct(a["mediroute"]["wrong"])],
             ["Asked the patient (or gave no usable speciality)", pct(a["asked"]), pct(a["mediroute"]["asked"])]]
    m = b["mediroute"]
    named, verified = b["hospitals_named"], round(b["hospitals_named"] * b["share_in_our_verified_list"])
    rows2 = [["How many hospitals were named (45 requests)", f"{named}", "5 per request"],
             ["<b>We can verify it</b>: it is in our checked list (NABH / JCI / own website)", f"<b>{pct(b['share_in_our_verified_list'])}</b> ({verified})", "<b>100%</b>"],
             ["<b>We cannot verify it</b>: not in our list (may be real, may not)", f"<b>{pct(1 - b['share_in_our_verified_list'])}</b> ({named - verified})", "0%"],
             ["Recommended a hospital in a different city than asked", pct(b["share_in_list_wrong_area"]),
              "0% (nearby cities only as a labelled “outside your area” group)"],
             ["<b>Can treat the need</b>: of the hospitals with a website-read grade, share with grade 2 or 3",
              f'{pct(b.get("share_judged_confirmed_capable"))} ({round(b["share_judged_confirmed_capable"] * b["judged_named_in_area"])} of {b.get("judged_named_in_area")})',
              f'{pct(m.get("share_judged_confirmed_capable"))} ({round(m["share_judged_confirmed_capable"] * m["judged_shown_in_area"])} of {m.get("judged_shown_in_area")})'],
             ["<b>At least one capable hospital in the first 3</b> (Capable@3)", f'{pct(b["capable_at3"])} ({round(b["capable_at3"] * b["n"])} of {b["n"]})',
              f'{pct(m["capable_at3"])} ({round(m["capable_at3"] * b["n"])} of {b["n"]})'],
             ["Ranking quality, NDCG@5 (supporting only, see note)", f'{b["ndcg5_judged"]:.2f}' if b["ndcg5_judged"] is not None else "–", f'{m["ndcg5_judged"]:.2f}']]
    ok, no, q = "✓", "✗", "?"
    examples = [
        ["<b>“Chest pain on exertion; cardiology in Guwahati.”</b>",
         f"Narayana Superspeciality, Amingaon: {q} not in our list (we only have its Howrah branch)<br>"
         f"Apollo Hospitals, Guwahati: {q} not in our list (we have Apollo in other cities)<br>"
         f"Health City Hospital: {ok} verified, in Guwahati, can treat (grade 2)<br>"
         f"GNRC Hospitals: {q} not in our list<br>Gauhati Medical College: {q} not in our list<br>"
         "<b>→ 1 of 5 can be verified</b>",
         f"Health City Hospital: {ok} grade 2<br>AIIMS Guwahati: {ok} grade 2<br>"
         "then, under <i>“Outside your area”</i> (only 2 cardiology hospitals in Guwahati in our data): Max Dehradun, Narayana Bengaluru, Ramesh Vijayawada<br>"
         "<b>→ 5 of 5 verified; the 2 local ones first</b>"],
        ["<b>“Head and neck cancer; oncologist recommended radiation therapy. Bengaluru.”</b>",
         f"HCG Cancer Centre: {q} not in our list (we only have HCG in Nashik)<br>"
         f"Mazumdar Shaw Medical Center: {q} not in our list<br>"
         f"Manipal Hospital, Whitefield: {ok} verified, can treat (grade 3)<br>"
         f"Cytecare Cancer Hospitals: {q} not in our list<br>Kidwai Memorial Institute of Oncology: {q} not in our list<br>"
         "<b>→ 1 of 5 can be verified</b>",
         f"Manipal (Old Airport Road), Narayana Health City, Fortis (Bannerghatta Road), Aster CMI: {ok} grade 2<br>"
         f"Sakra World Hospital: {ok} grade 3<br><b>→ 5 of 5 verified and in Bengaluru</b>"],
        ["<b>“Kidney failure; my brother will donate a kidney. Kidney transplant in Chennai.”</b>",
         f"Apollo (Greams Road), MGM Healthcare, Kauvery: {ok} grade 2<br>MIOT International: {ok} grade 3<br>"
         f"Dr. Rela Institute: {no} grade 0, but only a fallback grade (website unreadable)<br>"
         "<b>→ 5 of 5 verifiable: a good answer</b>",
         f"Sri Ramachandra, Gleneagles HealthCity, Rela Hospital: {ok} grade 2<br>MIOT International, SIMS: {ok} grade 3<br>"
         "<b>→ 5 of 5 verified</b>"],
    ]
    c = s.get("cost") or {}
    g_cost, m_cost = c.get("general_ai_per_answer"), c.get("mediroute_per_request")
    usd = lambda x, d=4: "–" if x is None else f"${x:.{d}f}"  # noqa: E731
    cost_rows = [["LLM cost per patient request", usd(g_cost), usd(m_cost, 5) + " (Step 1 + Step 2)"],
                 ["Per 1,000 requests", usd(g_cost * 1000 if g_cost else None, 2), usd(m_cost * 1000 if m_cost else None, 2)],
                 ["Relative cost", f"{g_cost / m_cost:.1f}×" if g_cost and m_cost else "–", "1×"],
                 ["Model", f"{e(s['model'])} (large)", "openai/gpt-6-luna (small) + local search"],
                 ["Answer length", f"{c.get('general_ai_output_tokens') or 0:.0f} output tokens on average", "fixed JSON answers"]]
    return f"""
<h1>9 · Compared with a general AI</h1>
{bullets([
    f"<b>General AI:</b> {e(s['model'])} via OpenRouter (low reasoning effort: a direct chat answer), given the patient's own words plus “Which medical speciality should I see, and which hospitals would you recommend? Please keep the answer short.” No system prompt, no hospital list, no tools.",
    f"Its free-text answers were turned into data by {e(s['extractor'])} (speciality mapped to our 26; hospitals named), then scored with the <b>same</b> test sets and website grades as MediRoute. Test cost ${s['spend_usd']:.2f}.",
])}
<h2>Speciality (the 100 portal-test messages)</h2>
{table(["", "General AI", "MediRoute"], rows1, ["50%", "25%", "25%"])}
<h2>Hospitals (the 45 Step 2 requests)</h2>
<p><b>How each hospital is checked.</b> Each request gives a need and a city. For every hospital an answer names we ask three
questions: (1) <b>Can we verify it?</b> Is it in our list of 201 hospitals checked against NABH, JCI and the hospital's own website?
(2) <b>Is it in the city the patient asked for?</b> (3) <b>Can it treat this need?</b> From the website grade: 0 cannot,
1 related only, 2 speciality confirmed, 3 speciality and procedure confirmed. “Can treat” = grade 2 or 3.
Symbols: {ok} verified and can treat · {q} cannot verify · {no} graded as cannot treat.</p>
<h2>Three real examples</h2>
{table(["Patient request", "General AI named", "MediRoute showed"], examples, ["22%", "41%", "37%"], "small")}
<h2>All 45 requests</h2>
{table(["", "General AI", "MediRoute"], rows2, ["48%", "22%", "30%"])}
<h2>Cost</h2>
{table(["", "General AI", "MediRoute"], cost_rows, ["50%", "20%", "30%"])}
<h2>What it shows</h2>
{bullets([
    "<b>Speciality: level.</b> The general AI scores slightly higher on correct answers (89% vs 85%) and asks less (4% vs 12%); it is confidently wrong more often (7% vs 3%), but 6 of its 7 misses send the patient to emergency care for chest-pain or breathing symptoms (cautious, not careless). None of these gaps is statistically significant (Fisher p = 0.53 and 0.33). We do <b>not</b> claim better speciality accuracy than a strong general AI.",
    "<b>Fair input:</b> both systems got the same text: the message plus the report text for the 15 core50 report cases (a first run without the reports made the AI ask for them and was discarded).",
    f"<b>Hospitals: the clear difference is verifiability.</b> {pct(1 - b['share_in_our_verified_list'])} of the hospitals it names cannot be checked against our NABH / JCI / website-verified list (often a local branch of a chain, or a hospital we never collected). It did keep to the patient's city. Every MediRoute result is from the verified list, with its reasons.",
    "<b>Quality of the hospitals it names</b> trends lower (confirmed capable 76% vs 86%; Capable@3 78% vs 93%), but the samples are small (p = 0.12 and 0.07): a direction, not proof.",
    "<b>Read with care:</b> a hospital not in our 201 is “not verifiable”, not necessarily wrong. NDCG favours MediRoute partly because its list could draw on 20 graded candidates while the general AI named at most 5, so the ‘confirmed capable’ share is the fairer quality measure. The API model is not the ChatGPT or Google app, which may also search the web. Hospital names were matched by code (chains: the AI's city, else the patient's area).",
])}
{where("scripts/compare_general_ai.py", f"data/evaluation/general_ai/{runs[-1].name}", "python scripts/compare_general_ai.py ask | pool | score")}
"""


def s_latency():
    rows = [
        ["End to end (browser → result), all 100", "2.55 s", "5.8 s", "6.5 s", "max 8.3 s"],
        ["… both voters agree (65)", "2.2 s", "–", "4.5 s", "no judge call"],
        ["… judge decided (23)", "5.1 s", "–", "7.1 s", "2 extra LLM calls in parallel"],
        ["… asked a question (12)", "4.3 s", "–", "6.5 s", ""],
        ["Step 1 inside the server", "2.5 s", "–", "6.5 s", ""],
        ["One LLM call (evidence or voter)", "1.9 s", "–", "3.6 s", "evidence + voter run in parallel"],
        ["One judge call", "2.2 s", "–", "–", ""],
        ["Step 2 (filter + FAISS + rerank)", "34 ms", "–", "53 ms", "no LLM"],
    ]
    cost = [["Hosted GPT-6 Luna (OpenRouter), current", "≈ $0.0004 / request", "2.6 s typical", "needs a key; 20 requests/min on a new account"],
            ["Local Ollama llama3.2 on a laptop CPU", "free", "p95 ≈ 67 s", "private; memory-heavy"],
            ["Free OpenRouter models (earlier)", "free", "2.5–15 s", "50 requests/day limit"],
            ["No LLM (search voters only)", "free", "< 1 s", "lower accuracy, more questions"]]
    return f"""
<h1>10 · Latency and cost</h1>
<p class="muted">Portal test of 11 Nov (100 requests, GPT-6 Luna, reasoning off); Step 2 from the workflow trace of the same run.</p>
{table(["Measure", "p50", "p90", "p95", "Note"], rows, ["38%", "11%", "11%", "11%", "29%"])}
<h2>Provider choice</h2>
{table(["Option", "Cost", "Speed", "Trade-off"], cost, ["34%", "20%", "16%", "30%"])}
{bullets([
    "Most of the wait is the LLM; Step 2 is negligible. Hidden “reasoning” is switched off (it was ~95% of the output and most of the wait).",
    "Evaluation spend so far: Step 2 trial and grading $0.15; general-AI comparison ≈ $0.4 (cap $1).",
])}
"""


def s_setup():
    return f"""
<h1>11 · Setup and API keys (for each team member)</h1>
<h2>Install once</h2>
<pre>git clone https://github.com/shubhamgithhub/MediRoute.git
cd MediRoute
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1          # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev,scraping]"
playwright install chromium            # only for scrapers and PDF reports</pre>
<h2>OpenRouter keys: one per person</h2>
{bullets([
    "<b>Account owner</b> (one shared, paid account): openrouter.ai → <b>Settings → API Keys → Create key</b>, one key per member, named after the person (e.g. “mediroute-member-a”), each with a <b>credit limit</b> (e.g. $2). Usage is then visible per person and any key can be revoked alone.",
    "Send each key <b>privately</b> (direct message, not the group, not e-mail threads). The key is shown only once at creation.",
    "<b>Each member</b> saves it once on their own machine and reopens VS Code / the terminal:<br><code>setx OPENROUTER_API_KEY \"sk-or-v1-…\"</code> (macOS/Linux: <code>export OPENROUTER_API_KEY=…</code> in ~/.zshrc or ~/.bashrc).",
    "<b>Never</b> commit a key, paste it into chat, a screenshot, a notebook or a log. If a key leaks: revoke it on the same page and create a new one.",
    "Check spend at openrouter.ai → Activity. A new account allows 20 requests per minute per model; the benchmark scripts pace themselves.",
    "No key? The app still runs: <code>$env:MEDIROUTE_LLM_PROVIDER = \"none\"</code> (search voters only) or install Ollama for a local model.",
])}
<h2>Start the app (two terminals)</h2>
<pre># Terminal 1: backend (port 8000)
.\\.venv\\Scripts\\Activate.ps1
$env:PYTHONPATH = "src"
$env:MEDIROUTE_LLM_PROVIDER = "openrouter"
$env:MEDIROUTE_OPENROUTER_MODEL = "openai/gpt-6-luna"   # the judge uses GPT-6 Luna by default
python -m uvicorn mediroute.backend.main:app --host 127.0.0.1 --port 8000

# Terminal 2: frontend (port 5500)
.\\.venv\\Scripts\\Activate.ps1
python scripts/serve_frontend.py      # no caching: every reload shows the latest files</pre>
{table(["Page", "URL"], [["Patient app", "http://127.0.0.1:5500/index.html"], ["Admin (request history, traces)", "http://127.0.0.1:5500/admin.html"],
                          ["API docs", "http://127.0.0.1:8000/docs"], ["Health check", "http://127.0.0.1:8000/api/health"]], ["45%", "55%"])}
<h2>Rerun things</h2>
<pre>python -m pytest -q                                   # 124 tests
python -m mediroute.data_generator.rebuild            # all processed data
python scripts/portal_benchmark.py --n 100 --spacing 15   # Step 1 through the running app
python scripts/eval_step2.py run --judged-only        # Step 2 benchmark
python scripts/build_team_report_pdf.py               # this report</pre>
"""


def s_limits():
    return f"""
<h1>12 · Limitations and next steps</h1>
<h2>Limitations</h2>
{bullets([
    "<b>Labels and rules are drafts:</b> test labels, 1,381 mapping rules and body-area rules await the doctor review; four “wrong” portal cases have questionable labels.",
    "<b>Hospital data:</b> 201 hospitals; procedure lists come from the team sheet and are unverified (~50% recall), which limits procedure matching.",
    "<b>Grades:</b> Step 2 grades are model-drafted from website snippets; 20% human spot-check pending; sites that block automated reading cannot be graded.",
    "<b>Scope:</b> English input only (no translation: Hinglish or regional-language messages often end in a question); text-based PDFs only (no OCR for scanned or photographed reports); no costs, doctor profiles, availability or booking.",
])}
<h2>Next steps</h2>
{bullets([
    "Doctor review of the drafts (docs/review/MediRoute_doctor_review.pdf), the report critical-detail labels (section 8c.1) and the 20% grade spot-check.",
    "Long reports: keep the end of the report (or its impression / diagnosis / plan sections) instead of only the first 6,000 characters; the one extraction failure in section 8c.1.",
    "Offline website extraction to fill the procedure lists, measured with the same Step 2 harness.",
    "Update the README (setup section still lists the old free models).",
    "Pick the final colour theme and remove the selector; replace the home-page demo card with real results.",
    "Close the readiness gaps in section 13 (tracker rows 46–56).",
])}
"""


def s_readiness():
    ok, part, gap = "✅ Done", "⚠️ Partly", "❌ Not done"
    return f"""
<h1>13 · Readiness review (12 Nov 2026)</h1>
<p class="subtitle">Where the project stands against the capstone grading areas, the final-submission checklist and the
mid-sem TA feedback. Items are paraphrased in our own words (the guidelines document is for personal use and is not
in the repository). Open items are tracked in <code>docs/PROJECT_TRACKER.md</code>, rows 46–56.</p>

<h2>Estimated marks (our own estimate, not the TA rubric)</h2>
{table(["Area (~25% each)", "Today", "After closing the gaps", "Why"], [
    ["Scope and impact", "19–21", "21–22", "Real problem, narrow and achievable scope (two steps, English, text PDFs). Gap: no domain expert has reviewed the labels yet."],
    ["Technical depth and execution", "17–19", "21–23", "Strong intelligence layer (rules + lookup + LLM voters + guarded judge; FAISS + transparent bonuses; LangGraph) and evaluation layer. Gap: no deployment or monitoring dashboard."],
    ["Presentation", "~17–20", "20–22", "Material is strong; risk is fitting it into 20 minutes. Needs a tight deck, a limitations slide and a backup demo video."],
    ["Viva (individual)", "~17–20", "20–22", "Each member must explain and defend their own part and redraw the architecture from memory."],
    ["<b>Total</b>", "<b>~70–80</b>", "<b>~82–89</b>", "Presentation and viva are half the marks and depend on delivery, not code."],
], widths=["22%", "10%", "15%", "53%"])}

<h2>Final-submission checklist</h2>
{table(["Item", "State", "What to do"], [
    ["System runs end to end", ok, "Patient page → Step 1 → Step 2 → hospital page."],
    ["Used by someone outside the team", gap, "3–5 outside users; note what confused them (one slide)."],
    ["Evaluation with a baseline", ok, "Step 1 and Step 2 baselines (sections 7–8); general-AI comparison (section 9)."],
    ["Deployed, with a dashboard of latency, cost and errors", gap, "Docker Compose, GitHub Actions (tests + eval gate), one cloud deployment, dashboard with p95 latency, cost per query, error rate."],
    ["Contribution log", gap, "docs/CONTRIBUTIONS.md (tracker row 38)."],
    ["Limitations, each with a named fix path", part, "Section 12 lists limitations; add the fix for each."],
    ["Demo recording as backup", gap, "Record the full flow once the screens are final."],
    ["Presentation rehearsed within time", gap, "20 minutes per group."],
], widths=["34%", "13%", "53%"])}

<h2>Good practice the graders look for</h2>
{table(["Practice", "State", "Note"], [
    ["One thing that works end to end", ok, "Translation, OCR, costs, hospital-side features dropped or deferred."],
    ["Real intelligence layer, not a thin web app", ok, "Sections 2–4."],
    ["Independent LLM judge", ok, "Judge and comparison models differ from the routed model."],
    ["Negative results reported", ok, "F1/F2 and the stronger judge: no gain, reverted (sections 6 and 7b)."],
    ["Cost and latency measured", part, "In evaluation runs (section 10); not tracked live per request."],
    ["Named versions of prompts, rules, configs", part, "Git history only; no list such as “judge prompt v3, ranker v2”."],
    ["Experiments log, one change per run", gap, "docs/EXPERIMENTS.md (tracker row 39); results already exist in data/evaluation/results."],
    ["Domain expert involved", gap, "Doctor review pending (docs/review/MediRoute_doctor_review.pdf)."],
    ["Demo not hardcoded", ok, "Live pipeline; the home-page card is labelled as illustrative."],
], widths=["34%", "13%", "53%"])}

<h2>Mid-sem TA feedback: follow-up</h2>
{table(["TA asked for", "State", "Note"], [
    ["Narrow the scope", ok, "Core = speciality routing + hospital ranking."],
    ["Verified hospital-speciality data; real vs simulated kept apart", ok, "Website + NABH/JCI data; team sheet marked “not verified”."],
    ["No costs or suitability shown as verified", ok, "Costs removed from screens; disclaimer box."],
    ["Baselines and Precision/Recall/NDCG@K", ok, "Show a keyword baseline next to semantic retrieval in the deck."],
    ["Extraction evaluated separately (accuracy, omissions)", ok, "Section 8c.1 (13 Nov): 93% of 85 critical details kept, 94% of decisive ones; losses located (LLM vs 6,000-character cut)."],
    ["Test alternative ranking weights, not arbitrary ones", ok, "Section 8c.2 (13 Nov): bonuses help (p = 0.02), exact values do not matter (×0.5 to ×4 within noise)."],
    ["Robustness: incomplete queries, noisy reports", part, "Unseen set, 31 PDF tests, typo cases; not yet one robustness section."],
    ["Medical suitability before location", part, "Area filter comes first (outside hospitals fill in when fewer than 3 are in the area). Prepare the answer or add a “best anywhere in India” option."],
    ["Expert-reviewed mappings and graded labels", gap, "Doctor review and 20% grade spot-check pending."],
    ["DPDP: consent, retention, access control", part, "Consent box, redaction, 100-request retention. Admin page has no login yet."],
], widths=["34%", "13%", "53%"])}

<h2>Priorities until 5 Dec</h2>
{bullets([
    "<b>1. Deployment and dashboard</b>: Docker, CI with an eval gate, cloud deployment, latency / cost / error dashboard.",
    "<b>2. Ranking-weight sensitivity test</b>: asked for directly by the TA; cheap.",
    "<b>3. Contribution and experiments logs</b>: mostly writing up what exists.",
    "<b>4. Doctor review and a safety set</b>: 30–50 emergency cases with a target of zero missed escalations.",
    "<b>5. Outside users, demo video, rehearsed deck</b> with limitations that name their fixes.",
])}
"""


CSS = """
@page { size: A4; }
body { font-family: "Segoe UI", Arial, sans-serif; color: #1d2733; font-size: 10.5pt; line-height: 1.45; }
section { page-break-after: always; }
section:last-child { page-break-after: auto; }
h1 { font-size: 19pt; margin: 0 0 8px; color: #1e2a5a; border-bottom: 3px solid #3b3f8f; padding-bottom: 4px; }
h2 { font-size: 12.5pt; margin: 14px 0 6px; color: #2c2f6e; }
.subtitle { color: #5c6878; margin: 0 0 14px; }
.muted { color: #6a7584; font-size: 9pt; }
.ta { margin: 4px 0 10px; padding: 8px 12px; border-left: 4px solid #d9932f; background: #fff7e8; border-radius: 4px; font-size: 10pt; line-height: 1.45; }
ul { margin: 4px 0 8px 18px; padding: 0; } li { margin: 3px 0; }
table { width: 100%; border-collapse: collapse; margin: 6px 0 10px; font-size: 9.5pt; }
table.small { font-size: 8.6pt; }
th { background: #eceef8; color: #1e2a5a; text-align: left; padding: 5px 6px; border-bottom: 2px solid #c9cce6; }
td { padding: 4px 6px; border-bottom: 1px solid #e4e6ef; vertical-align: top; }
code, pre { font-family: Consolas, monospace; font-size: 8.8pt; }
code { background: #f1f2f7; padding: 0 3px; border-radius: 3px; }
pre { background: #f5f6fa; border: 1px solid #e1e3ee; border-radius: 6px; padding: 8px 10px; white-space: pre-wrap; }
.tiles { display: flex; gap: 8px; margin: 6px 0 12px; }
.tile { flex: 1; border: 1px solid #d9dcef; border-top: 4px solid #3b3f8f; border-radius: 8px; padding: 8px; }
.tile b { display: block; font-size: 17pt; color: #1e2a5a; } .tile span { display: block; font-weight: 600; font-size: 9pt; }
.tile small { color: #6a7584; font-size: 8pt; }
.flow { display: flex; align-items: stretch; gap: 4px; margin: 8px 0 10px; }
.box { flex: 1; border-radius: 8px; padding: 7px 8px; border: 1.5px solid; font-size: 8.8pt; }
.box b { display: block; font-size: 9.6pt; } .box span { color: #4b5563; }
.box.ai { background: #efeefe; border-color: #8b80d8; } .box.code { background: #e9f6ef; border-color: #6fb08b; }
.box.data { background: #f2f1ee; border-color: #a8a297; } .box.out { background: #fff6e6; border-color: #e0a84a; }
.arrow { align-self: center; color: #6a7584; font-size: 14pt; }
.where { margin-top: 8px; padding: 6px 8px; background: #f7f7fb; border-left: 3px solid #3b3f8f; font-size: 8.8pt; color: #3d4757; }
.chart { width: 100%; max-height: 330px; object-fit: contain; margin-top: 6px; }
.legend { font-size: 8.5pt; color: #6a7584; }
"""


def build_html() -> str:
    legend = ('<p class="legend">Boxes: <span style="color:#6a5fc7">■</span> AI (LLM or embeddings) · '
              '<span style="color:#3f8a60">■</span> code · <span style="color:#8c867b">■</span> input / data · '
              '<span style="color:#c98b20">■</span> output</p>')
    sections = [s_summary(), s_use_case(), s_architecture() + legend, s_step1(), s_step2(), s_data(), s_evolution(),
                s_bench1(), s_bench2(), s_ta_benchmarks(), s_general_ai(), s_latency(), s_setup(), s_limits(), s_readiness()]
    body = "".join(f"<section>{s}</section>" for s in sections)
    return f'<!doctype html><html><head><meta charset="utf-8"><title>MediRoute team report</title><style>{CSS}</style></head><body>{body}</body></html>'


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    html_path, pdf_path = OUT_DIR / "MediRoute_team_report.html", OUT_DIR / "MediRoute_team_report.pdf"
    html_path.write_text(build_html(), encoding="utf-8")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(html_path.resolve().as_uri(), wait_until="load")
        try:  # one report only: if a viewer has it open (Windows locks it), stop instead of writing a copy
            with pdf_path.open("ab"):
                pass
        except PermissionError:
            browser.close()
            raise SystemExit(f"{pdf_path.name} is open in another program; close it and run this again.")
        page.pdf(path=str(pdf_path), format="A4", print_background=True, display_header_footer=True,
                 header_template="<span></span>",
                 footer_template='<div style="font-size:7pt;color:#777;width:100%;text-align:center">'
                                 'MediRoute team report · academic capstone project · page <span class="pageNumber"></span> of '
                                 '<span class="totalPages"></span></div>',
                 margin={"top": "14mm", "bottom": "16mm", "left": "14mm", "right": "14mm"})
        browser.close()
    print(f"Wrote {pdf_path}")


if __name__ == "__main__":
    main()
