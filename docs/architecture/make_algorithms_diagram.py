"""MediRoute algorithms: what each stage computes, with its weights and one real worked example.

    python docs/architecture/make_algorithms_diagram.py

Writes mediroute_algorithms.html and mediroute_algorithms.png next to this file. This is the detailed
companion of mediroute_pipeline_architecture (the main flow diagram, kept as it is). Thresholds and
weights are read from the code, so the diagram matches what runs. The worked example is request
c9fc0f982f48 (13 Nov 2026, GPT-6 Luna via OpenRouter, city Mumbai); the admin page shows the same
numbers for any request.
"""
from __future__ import annotations

import sys
from html import escape as e
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

from mediroute.hospital_recommendation.engine import HospitalRecommendationEngine  # noqa: E402
from mediroute.hospital_recommendation.ranking.hospital_reranker import WEIGHTS  # noqa: E402
from mediroute.specialty_routing.step1 import voters as V  # noqa: E402

W = WEIGHTS
EXAMPLE = "I have acid reflux and stomach pain for months, doctor suggested endoscopy"

# (number, kind, title, why, algorithm lines, parameters / weights, example in, example out)
STEP1 = [
    ("1", "code", "Protect", "Personal details never reach a model or the log.",
     ["Regular expressions find phone numbers, e-mails and ID numbers",
      "Each is replaced by [PHONE] / [EMAIL] / [ID]"],
     [], EXAMPLE, "unchanged (nothing to hide)"),
    ("2", "code", "Emergency check", "Red flags get a notice on top; routing still continues.",
     ["Fixed red-flag rules (crushing chest pain, stroke signs, suicidal words…)"],
     [], "same text", "no emergency"),
    ("3", "llm", "Evidence · LLM call 1", "Pull out only the medical words, so the lookup is not misled by the rest.",
     ["LLM copies conditions, procedures and body parts word for word (JSON schema, ≤ 6 per list)",
      "Code keeps a phrase only if ≥ 60% of its words are in the text (exact, abbreviation, or spelling similarity ≥ 0.85)",
      "Generic words and phrases with [PHONE]/[EMAIL]/[ID] are dropped",
      "Code adds everyday terms found word for word (keyword matches)",
      "Phrases for V1 = conditions + procedures + keyword matches (body parts only if nothing else)"],
     ["prompt evidence_v1", "temperature 0, seed 7", "≈ 258 prompt tokens, 2–3 s"],
     "fixed instruction + the message",
     'LLM: {"conditions":["acid reflux","stomach pain"], "procedures":["endoscopy"], "body_parts":["stomach"]}\n'
     "check: all 4 kept (100% of words found)\n→ V1 phrases: acid reflux · stomach pain · endoscopy"),
    ("4a", "ml", "V1 lookup voter · no LLM", "An independent check against fixed medical data.",
     ["Per phrase: remove generic words",
      "Keyword search: TF-IDF, 0.5 × word (1–2 words) + 0.5 × character (3–5 letters), cosine",
      "Meaning search: all-MiniLM-L6-v2 sentence embeddings, cosine",
      f"Fuse by rank (Reciprocal Rank Fusion): score = Σ 1 / ({V.RRF_K} + rank)",
      f"Each phrase votes once: best entry's speciality full score, its other specialities × {V.RUNNER_UP_WEIGHT}",
      "Sum over phrases; General Medicine dropped if any specialist matched"],
     [f"keyword min score {V.KEYWORD_MIN_SCORE}", f"meaning min score {V.EMBEDDING_MIN_SCORE}",
      f"top {V.FUSION_DEPTH} from each search", f"RRF k = {V.RRF_K}", f"top {V.HITS_PER_PHRASE} entries per phrase",
      f"runner-up weight × {V.RUNNER_UP_WEIGHT}", f"symptom / weak term × {V.WEAK_EVIDENCE_WEIGHT}",
      "lookup: 10,884 entries (ICD-10-CM via AHRQ CCSR, CGHS, everyday terms)"],
     "acid reflux · stomach pain · endoscopy",
     "acid reflux → everyday term #1 in both searches (0.0328); K21 GERD (keyword #7, meaning #2)\n"
     "endoscopy → CGHS MG001 Upper GI endoscopy; ENT “endoscopy under GA” counted × 0.1\n"
     "totals: Gastroenterology 0.0971 · Urology 0.0060 · ENT 0.0032\n→ V1: Gastroenterology"),
    ("4b", "llm", "V2 AI voter · LLM call 2", "An independent opinion from the whole message; never sees V1.",
     ["LLM reads rules + every speciality (description, route here when, not here) + the message",
      "Must answer one name from the list or “Unclear” (JSON schema enum; code checks again)",
      "Up to 2 alternatives; cites the words that drove the choice",
      "Scores by rank 1.0 / 0.5 / 0.33: a choice, not a probability"],
     ["prompt specialty_v2", "temperature 0, seed 7", "≈ 2,477 prompt tokens, 2–3 s",
      "runs at the same time as call 1 (hosted model)"],
     "≈ 10,000-character prompt + the message",
     '{"specialty":"Gastroenterology", "alternatives":[], "evidence_terms":["acid reflux","stomach pain","endoscopy"]}\n'
     "→ V2: Gastroenterology"),
    ("5", "code", "Decide · first rule that matches", "Agreement of two independent voters is the main signal.",
     ["V1 = V2 → that speciality",
      "Differ, and the patient's body-area answer fits exactly one → that one",
      "Differ otherwise → AI judge (5b)",
      "V2 “Unclear”, no phrases, or judge unsure → ask the patient",
      "AI unavailable → V1 alone, with a notice",
      "General Medicine on the first try → ask once more"],
     [], "V1 Gastroenterology, V2 Gastroenterology", "agreement → Gastroenterology"),
    ("5b", "llm", "AI judge · LLM calls 3 + 4 (only if V1 ≠ V2)", "Settles a disagreement without inventing anything.",
     ["Closed choice: only the two candidates or “unclear”",
      "Must cite evidence lines built by code from the lookup; code checks they exist and support the choice",
      "Its quote must be in the patient's text",
      "Asked twice with the candidates swapped; both answers must match, else ask the patient"],
     ["prompt judge_v1", "GPT-6 Luna, reasoning off", "≈ $0.0001 per disagreement"],
     "not run here (voters agreed)", "—"),
]

STEP2 = [
    ("1", "code", "Eligible hospitals", "Only hospitals that offer the speciality, in the chosen area.",
     ["Speciality must be in the hospital's list (own website = verified; team sheet = marked unverified)",
      "City or state filter from cities.csv"],
     ["201 hospitals in hospitals.csv"], "Gastroenterology · Mumbai", "143 offer it · 12 in Mumbai"),
    ("2", "ml", "Similarity search", "Order eligible hospitals by how well their services match the request.",
     ["Query text = speciality + diagnoses + procedures (+ findings)",
      "multi-qa-MiniLM-L6-cos-v1 embeddings; FAISS IndexFlatIP on normalised vectors = cosine",
      "Search only the eligible hospitals; take 3 × the number needed"],
     ["top_k 5 → 15 candidates (12 available here)"],
     "“Specialty: Gastroenterology. Diagnoses: acid reflux, stomach pain. Relevant procedures: endoscopy…”",
     "semantic scores, e.g. Wockhardt Mumbai Central 0.385 · Hinduja 0.375 · Fortis Mulund 0.362"),
    ("3", "code", "Transparent bonuses", "Small, explainable extras; each one becomes a ranking reason.",
     ["final score = semantic score + bonus",
      f"bonus = min({W['bonus_cap']}, sum of the parts)"],
     [f"website-confirmed speciality +{W['website_specialty']}",
      f"each matching procedure +{W['procedure_each']} (max {W['procedure_max']})",
      f"verified details +{W['verified']} (partially +{W['partially_verified']})",
      f"NABH +{W['nabh']} · JCI +{W['jci']}", f"international patient services +{W['international_patients']}",
      f"evidence quality up to +{W['evidence_max']} (High / Medium / Low)", f"cap {W['bonus_cap']}"],
     "the 12 candidates",
     "Wockhardt 0.385 + 0.16 = 0.545 (#1)\nFortis Mulund 0.362 + 0.16 = 0.522 (#2)\n"
     "Hinduja 0.375 + 0.14 = 0.515 (#3: no JCI)\n(no hospital listed “endoscopy”, so no procedure bonus)"),
    ("4", "code", "Outside-area group", "Never leave the patient with fewer than 3 options.",
     [f"Fewer than {HospitalRecommendationEngine.MIN_IN_AREA} in the area → add the same state, then the rest of India",
      "Shown as a separate, labelled group"],
     [], "5 found in Mumbai", "not needed"),
]

KIND = {"llm": ("LLM", "#efeafe", "#7c6bd6"), "ml": ("ML search (code)", "#e6f1fd", "#3f86d4"),
        "code": ("Deterministic code / rules", "#e7f5ec", "#3f9a65")}


def card(step) -> str:
    num, kind, title, why, algo, params, ex_in, ex_out = step
    label, bg, border = KIND[kind]
    algo_html = "".join(f"<li>{e(a)}</li>" for a in algo)
    params_html = "".join(f'<span class="p">{e(p)}</span>' for p in params) or '<span class="none">—</span>'
    return (f'<div class="card" style="border-color:{border}">'
            f'<div class="title" style="background:{bg}"><span class="num" style="background:{border}">{e(num)}</span>'
            f'<b>{e(title)}</b><span class="kind" style="color:{border}">{e(label)}</span></div>'
            f'<div class="grid"><div><div class="h">Why</div><div class="why">{e(why)}</div>'
            f'<div class="h">Algorithm</div><ol>{algo_html}</ol></div>'
            f'<div><div class="h">Parameters / weights</div><div class="params">{params_html}</div></div>'
            f'<div class="ex"><div class="h">Example</div><div class="in">in: {e(ex_in)}</div>'
            f'<div class="out">{e(ex_out)}</div></div></div></div>')


def build() -> str:
    arrow = '<div class="arrow">▼</div>'
    legend = "".join(f'<span class="lg"><i style="background:{bg};border-color:{bd}"></i>{e(lb)}</span>'
                     for lb, bg, bd in KIND.values())
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>MediRoute algorithms</title><style>
body{{margin:0;background:#fff;font-family:"Segoe UI",Arial,sans-serif;color:#1d2733}}
.wrap{{width:1440px;padding:28px 36px}} h1{{font-size:26px;margin:0 0 6px;color:#1e2a5a}}
.sub{{color:#5b6676;font-size:14px;margin-bottom:12px;line-height:1.5}}
.legend{{display:flex;gap:22px;margin:0 0 16px;font-size:14px}}
.lg i{{display:inline-block;width:16px;height:16px;border:2px solid;border-radius:4px;vertical-align:-3px;margin-right:6px}}
.group{{border:2px dashed #b9bfcc;border-radius:14px;padding:12px 14px 14px;margin-bottom:18px}}
.gtitle{{font-weight:800;color:#1e2a5a;font-size:16px;margin:0 0 10px;letter-spacing:.4px}}
.card{{border:2px solid;border-radius:10px;overflow:hidden;background:#fff}}
.title{{display:flex;align-items:center;gap:10px;padding:7px 12px;font-size:16px}}
.num{{color:#fff;font-weight:800;font-size:13px;border-radius:6px;padding:2px 8px}}
.kind{{margin-left:auto;font-size:11px;font-weight:800;letter-spacing:.8px;text-transform:uppercase}}
.grid{{display:grid;grid-template-columns:1.25fr .8fr 1.15fr;gap:16px;padding:8px 14px 12px;font-size:13.5px;line-height:1.45}}
.h{{font-size:11px;font-weight:800;letter-spacing:.7px;text-transform:uppercase;color:#6a7584;margin:4px 0 3px}}
.why{{color:#3b4757;margin-bottom:4px}} ol{{margin:0;padding-left:18px}} li{{margin:1px 0}}
.params{{display:flex;flex-wrap:wrap;gap:5px}} .p{{background:#f3f2ef;border:1.5px solid #a39d92;border-radius:6px;padding:2px 8px;font-size:12.5px}}
.none{{color:#b0aaa0}} .ex .in{{color:#5b6676;margin-bottom:4px}}
.out{{white-space:pre-wrap;font-family:Consolas,monospace;font-size:12.5px;background:#f7f8fa;border:1px solid #e1e5ea;border-radius:6px;padding:6px 8px}}
.arrow{{text-align:center;color:#8a93a0;font-size:15px;line-height:20px}}
.note{{font-size:13px;color:#5b6676;margin-top:6px}}
</style></head><body><div class="wrap">
<h1>MediRoute algorithms: what each stage computes</h1>
<div class="sub">Detailed companion of the main flow diagram (mediroute_pipeline_architecture.png). Weights and thresholds are read
from the code. Worked example (13 Nov 2026, GPT-6 Luna, Mumbai): “{e(EXAMPLE)}”. The admin page shows these numbers for any request.</div>
<div class="legend">{legend}</div>
<div class="group"><div class="gtitle">STEP 1 · patient words → speciality to search (2 LLM calls; 4 if the voters disagree)</div>
{arrow.join(card(s) for s in STEP1)}</div>
<div class="group"><div class="gtitle">STEP 2 · speciality → ranked hospitals (no LLM)</div>
{arrow.join(card(s) for s in STEP2)}
<div class="note">Output: top 5 with the reasons for each bonus; outside-area hospitals are labelled.</div></div>
</div></body></html>"""


def main() -> None:
    html_path = HERE / "mediroute_algorithms.html"
    html_path.write_text(build(), encoding="utf-8")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1520, "height": 900}, device_scale_factor=1.5)
        page.goto(html_path.resolve().as_uri(), wait_until="load")
        page.locator(".wrap").screenshot(path=str(HERE / "mediroute_algorithms.png"))
        browser.close()
    print(f"Wrote {html_path.name} and mediroute_algorithms.png")


if __name__ == "__main__":
    main()
