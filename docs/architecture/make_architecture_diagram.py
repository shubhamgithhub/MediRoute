"""Generate the MediRoute pipeline diagram (SVG + PNG).

    python docs/architecture/make_architecture_diagram.py

Writes mediroute_pipeline_architecture.svg and .png next to this file. Edit the layout below
when the pipeline changes. The PNG is rendered with Playwright's Chromium (already used by the
scrapers). The previous hand-made diagram is kept as mediroute_pipeline_architecture_v1.png.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parents[1] / "data"


def count_rows(path: Path) -> str:
    """Data rows in a CSV, so the diagram's numbers follow the data."""
    with path.open(encoding="utf-8-sig") as handle:
        return f"{sum(1 for _ in handle) - 1:,}"


N_LOOKUP = count_rows(DATA / "medical_taxonomy" / "step1_lookup.csv")
N_HOSPITALS = count_rows(DATA / "processed" / "hospitals.csv")
U = 80  # pixels per layout unit
W, H = 12.0, 21.8

STYLE = {  # fill, border, title colour, subtitle colour
    "llm": ("#EEEDFD", "#6A5ACD", "#3B2E8C", "#5B4DB0"),
    "code": ("#E3F4EE", "#2E8B6A", "#0F5C40", "#1F7A58"),
    "data": ("#F2EFEA", "#6B6B6B", "#333333", "#555555"),
    "planned": ("#FFFFFF", "#9A9A9A", "#555555", "#777777"),
}
parts: list[str] = []


def px(v: float) -> float:
    return round(v * U, 1)


def box(cx, cy, w, h, title, sub, kind):
    fill, edge, tcol, scol = STYLE[kind]
    x, y = cx - w / 2, cy - h / 2
    parts.append(f'<rect x="{px(x)}" y="{px(y)}" width="{px(w)}" height="{px(h)}" rx="11" '
                 f'fill="{fill}" stroke="{edge}" stroke-width="1.6"'
                 + (' stroke-dasharray="7 4"' if kind == "planned" else "") + '/>')
    ty = cy - 0.12 if sub else (cy - h / 2 + 0.4 if kind == "planned" else cy + 0.07)
    parts.append(f'<text x="{px(cx)}" y="{px(ty)}" text-anchor="middle" font-size="17" font-weight="700" '
                 f'fill="{tcol}">{escape(title)}</text>')
    if sub:
        parts.append(f'<text x="{px(cx)}" y="{px(cy + 0.25)}" text-anchor="middle" font-size="13" '
                     f'fill="{scol}">{escape(sub)}</text>')


def arrow(*points, label=None, label_at=None, dashed=False):
    pts = " ".join(f"{px(x)},{px(y)}" for x, y in points)
    dash = ' stroke-dasharray="6 4"' if dashed else ""
    parts.append(f'<polyline points="{pts}" fill="none" stroke="#4A4A4A" stroke-width="1.6"{dash} '
                 f'marker-end="url(#arrow)"/>')
    if label:
        lx, ly = label_at or points[len(points) // 2]
        parts.append(f'<text x="{px(lx)}" y="{px(ly)}" font-size="12.5" font-style="italic" fill="#4A4A4A">'
                     f'{escape(label)}</text>')


def line(*points):
    pts = " ".join(f"{px(x)},{px(y)}" for x, y in points)
    parts.append(f'<polyline points="{pts}" fill="none" stroke="#4A4A4A" stroke-width="1.6"/>')


def container(x0, y0, x1, y1, title, anchor="end"):
    parts.append(f'<rect x="{px(x0)}" y="{px(y0)}" width="{px(x1 - x0)}" height="{px(y1 - y0)}" rx="16" '
                 f'fill="none" stroke="#B5B5B5" stroke-width="1.4" stroke-dasharray="7 5"/>')
    tx = x1 - 0.25 if anchor == "end" else x0 + 0.25
    parts.append(f'<text x="{px(tx)}" y="{px(y0 + 0.45)}" text-anchor="{anchor}" font-size="18" '
                 f'font-weight="700" fill="#1F2A44">{escape(title)}</text>')


def text(x, y, value, size=13, weight="400", anchor="start", colour="#555555"):
    parts.append(f'<text x="{px(x)}" y="{px(y)}" text-anchor="{anchor}" font-size="{size}" '
                 f'font-weight="{weight}" fill="{colour}">{escape(value)}</text>')


# ------------------------------------------------------------------ title and input
text(0.3, 0.6, "MediRoute: two-step hospital discovery pipeline", size=24, weight="700", colour="#1F2A44")
box(6.0, 1.55, 5.4, 0.9, "Patient input", "query text · optional report text (PDF)", "data")

# ------------------------------------------------------------------ Step 1
container(0.3, 2.35, 11.7, 14.05, "Step 1: patient input to suggested speciality")
box(6.0, 3.35, 6.6, 0.95, "Protect + emergency rules", "remove phone / e-mail / IDs · red flags add a notice", "code")
arrow((6.0, 2.0), (6.0, 2.875))
box(7.9, 4.95, 6.6, 1.05, "Extract evidence", "LLM copies conditions, procedures, body parts + keywords", "llm")
box(2.45, 4.95, 3.3, 1.05, f"Lookup list ({N_LOOKUP})", "ICD-10-CM + CGHS + lay terms", "data")
arrow((6.0, 3.825), (6.0, 4.2), (7.9, 4.2), (7.9, 4.425))

# data correction: clean the evidence before anyone votes on it
box(7.9, 6.3, 6.6, 1.2, "Clean evidence (data correction)",
    "keep phrases found in the text · drop generic words", "code")
text(7.9, 6.78, "e.g. drops 'treatment', 'hospital', 'Mumbai', 'since last month'",
     size=12, anchor="middle", colour="#1F7A58")
arrow((7.9, 5.475), (7.9, 5.7))

# voters
box(2.4, 8.25, 3.2, 1.05, "V1 keyword search", "TF-IDF over lookup list", "code")
box(6.0, 8.25, 3.2, 1.05, "V2 meaning search", "embeddings over lookup list", "llm")
box(9.6, 8.25, 3.2, 1.05, "V3 local LLM", "picks from 26-speciality list", "llm")
# lookup list feeds V1 and V2
arrow((1.6, 5.475), (1.6, 7.725))
arrow((3.6, 5.475), (3.6, 7.15), (5.3, 7.15), (5.3, 7.725))
# cleaned evidence feeds all three voters
line((7.9, 6.9), (7.9, 7.4))
line((2.9, 7.4), (9.6, 7.4))
arrow((2.9, 7.4), (2.9, 7.725))
arrow((6.6, 7.4), (6.6, 7.725))
arrow((9.6, 7.4), (9.6, 7.725))

# majority
box(6.0, 10.05, 6.6, 1.05, "Majority vote", "2 of 3 agree + evidence in the text", "code")
line((2.4, 8.775), (2.4, 9.15), (9.6, 9.15))
line((9.6, 8.775), (9.6, 9.15))
line((6.0, 8.775), (6.0, 9.15))
arrow((6.0, 9.15), (6.0, 9.525))

# clarification loop and output
box(2.75, 11.65, 4.6, 1.05, "Clarification form", "max 2 rounds, then user picks", "code")
box(9.0, 11.65, 4.6, 1.05, "Suggested speciality", "to search, with evidence + disclaimer", "code")
arrow((4.5, 10.575), (4.5, 11.125), label="no majority", label_at=(3.35, 10.92))
arrow((7.5, 10.575), (7.5, 11.125), label="yes", label_at=(7.62, 10.92))
arrow((5.05, 11.65), (6.7, 11.65), label="user picks", label_at=(5.25, 11.52))
# loop back from the clarification form (left edge at x=0.45) to the evidence stage
arrow((0.45, 11.65), (0.45, 4.02), (5.2, 4.02), (5.2, 4.425), dashed=True)
text(0.55, 9.6, "answers added,", size=12.5, colour="#4A4A4A")
text(0.55, 9.85, "re-run", size=12.5, colour="#4A4A4A")

box(4.0, 13.25, 7.0, 0.85, "Per-request trace", "logs/step1_trace.jsonl: input, LLM calls, votes, decision", "data")

# ------------------------------------------------------------------ Step 2 (as built: hospital_recommendation/engine.py)
container(0.3, 14.45, 11.7, 20.75, "Step 2: speciality to ranked hospitals (HospitalRecommendationEngine)", anchor="start")
arrow((9.0, 12.175), (9.0, 15.075))

# R1: hard filters, with the two no-match exits
box(9.0, 15.55, 4.6, 0.95, "Hard filters", "speciality (website or team list) · search area", "code")
box(3.0, 15.55, 4.6, 0.95, "No match", "no speciality: say so · no city: ask to widen", "code")
arrow((6.7, 15.55), (5.3, 15.55), label="none left", label_at=(5.45, 15.42))

# R2: semantic search over the filtered hospitals only
box(3.0, 17.0, 4.6, 0.95, f"Hospital table ({N_HOSPITALS})", "hospitals.csv, shared with Step 1 · FAISS", "data")
box(9.0, 17.0, 4.6, 1.2, "Semantic search", "query: speciality + diagnoses + procedures", "llm")
text(9.0, 17.48, "multi-qa-MiniLM cosine · top 3×K candidates", size=12, anchor="middle", colour="#5B4DB0")
arrow((9.0, 16.025), (9.0, 16.4))
arrow((5.3, 17.0), (6.7, 17.0))

# R3: transparent rule bonus
box(9.0, 18.5, 4.6, 1.2, "Rerank: semantic + bonus", "bonus ≤ 0.20, each one listed as a reason", "code")
text(9.0, 18.98, "website .04 · procedure ≤.08 · verified .03 · NABH · JCI · intl .02", size=11.5, anchor="middle",
     colour="#1F7A58")
arrow((9.0, 17.6), (9.0, 17.9))

# R4: result
box(9.0, 19.95, 4.6, 0.95, "Ranked hospitals (top 5)", "final score + ranking reasons", "code")
arrow((9.0, 19.1), (9.0, 19.475))

# planned, not built (TA: test weights, ground explanations)
box(3.0, 19.25, 4.6, 2.0, "Planned, not built yet", "", "planned")
for i, item in enumerate(["AHP-TOPSIS: tested weights (fit > location)",
                          "grounded LLM explanation per hospital",
                          "keyword + FAISS hybrid retrieval",
                          "CGHS cost (display only, deferred)"]):
    text(0.95, 19.0 + i * 0.36, "· " + item, size=12.5, colour="#666666")

# ------------------------------------------------------------------ legend
for i, (kind, label) in enumerate([("llm", "LLM or embeddings"), ("code", "Deterministic code"),
                                   ("data", "Input or data"), ("planned", "Planned")]):
    fill, edge, _, _ = STYLE[kind]
    x = 0.5 + i * 2.95
    dash = ' stroke-dasharray="5 3"' if kind == "planned" else ""
    parts.append(f'<rect x="{px(x)}" y="{px(21.15)}" width="22" height="22" rx="5" fill="{fill}" stroke="{edge}"{dash}/>')
    text(x + 0.42, 21.38, label, size=15, colour="#333333")

svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{px(W)}" height="{px(H)}" viewBox="0 0 {px(W)} {px(H)}" '
       f'font-family="Inter, Segoe UI, Helvetica, Arial, sans-serif">'
       '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" '
       'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#4A4A4A"/></marker></defs>'
       f'<rect width="100%" height="100%" fill="#FFFFFF"/>{"".join(parts)}</svg>')

svg_path = HERE / "mediroute_pipeline_architecture.svg"
svg_path.write_text(svg, encoding="utf-8")

from playwright.sync_api import sync_playwright  # noqa: E402

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": int(px(W)), "height": int(px(H))}, device_scale_factor=2)
    page.set_content(f'<html><body style="margin:0">{svg}</body></html>')
    page.locator("svg").screenshot(path=str(HERE / "mediroute_pipeline_architecture.png"))
    browser.close()
print("wrote", svg_path, "and .png")
