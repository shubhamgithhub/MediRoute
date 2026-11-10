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
U = 80  # pixels per layout unit
W, H = 12.0, 21.2

STYLE = {  # fill, border, title colour, subtitle colour
    "llm": ("#EEEDFD", "#6A5ACD", "#3B2E8C", "#5B4DB0"),
    "code": ("#E3F4EE", "#2E8B6A", "#0F5C40", "#1F7A58"),
    "data": ("#F2EFEA", "#6B6B6B", "#333333", "#555555"),
}
parts: list[str] = []


def px(v: float) -> float:
    return round(v * U, 1)


def box(cx, cy, w, h, title, sub, kind):
    fill, edge, tcol, scol = STYLE[kind]
    x, y = cx - w / 2, cy - h / 2
    parts.append(f'<rect x="{px(x)}" y="{px(y)}" width="{px(w)}" height="{px(h)}" rx="11" '
                 f'fill="{fill}" stroke="{edge}" stroke-width="1.6"/>')
    ty = cy - 0.12 if sub else cy + 0.07
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
container(0.3, 2.35, 11.7, 12.75, "Step 1: patient input to suggested speciality")
box(6.0, 3.35, 6.6, 0.95, "Protect + emergency rules", "remove phone / e-mail / IDs · red flags add a notice", "code")
arrow((6.0, 2.0), (6.0, 2.875))
box(7.9, 4.95, 6.6, 1.05, "Extract evidence", "LLM + speciality keywords; code keeps phrases in the text", "llm")
box(2.45, 4.95, 3.3, 1.05, "Lookup list (10,584)", "ICD-10-CM + CGHS to speciality", "data")
arrow((6.0, 3.825), (6.0, 4.2), (7.9, 4.2), (7.9, 4.425))

# voters
box(2.4, 6.95, 3.2, 1.05, "V1 keyword search", "TF-IDF over lookup list", "code")
box(6.0, 6.95, 3.2, 1.05, "V2 meaning search", "embeddings over lookup list", "llm")
box(9.6, 6.95, 3.2, 1.05, "V3 local LLM", "picks from 26-speciality list", "llm")
# lookup list feeds V1 and V2
arrow((1.6, 5.475), (1.6, 6.425))
arrow((3.6, 5.475), (3.6, 5.85), (5.3, 5.85), (5.3, 6.425))
# evidence feeds all three voters
line((7.9, 5.475), (7.9, 6.1))
line((2.9, 6.1), (9.6, 6.1))
arrow((2.9, 6.1), (2.9, 6.425))
arrow((6.6, 6.1), (6.6, 6.425))
arrow((9.6, 6.1), (9.6, 6.425))

# majority
box(6.0, 8.75, 6.6, 1.05, "Majority vote", "2 of 3 agree + evidence in the text", "code")
line((2.4, 7.475), (2.4, 7.85), (9.6, 7.85))
line((9.6, 7.475), (9.6, 7.85))
line((6.0, 7.475), (6.0, 7.85))
arrow((6.0, 7.85), (6.0, 8.225))

# clarification loop and output
box(2.75, 10.35, 4.6, 1.05, "Clarification form", "max 2 rounds, then user picks", "code")
box(9.0, 10.35, 4.6, 1.05, "Suggested speciality", "to search, with evidence + disclaimer", "code")
arrow((4.5, 9.275), (4.5, 9.825), label="no majority", label_at=(3.35, 9.62))
arrow((7.5, 9.275), (7.5, 9.825), label="yes", label_at=(7.62, 9.62))
arrow((5.05, 10.35), (6.7, 10.35), label="user picks", label_at=(5.25, 10.22))
# loop back from the clarification form (left edge at x=0.45) to the evidence stage
arrow((0.45, 10.35), (0.45, 4.02), (5.2, 4.02), (5.2, 4.425), dashed=True)
text(0.55, 8.0, "answers added,", size=12.5, colour="#4A4A4A")
text(0.55, 8.25, "re-run", size=12.5, colour="#4A4A4A")

box(4.0, 11.95, 7.0, 0.85, "Per-request trace", "logs/step1_trace.jsonl: input, LLM calls, votes, decision", "data")

# ------------------------------------------------------------------ Step 2 (unchanged)
container(0.3, 13.15, 11.7, 20.05, "Step 2: speciality to ranked hospitals", anchor="start")
arrow((9.0, 10.875), (9.0, 14.225))
box(3.0, 14.75, 4.6, 0.95, "Verified hospital data", "NABH / JCI + websites (100 hospitals)", "data")
box(9.0, 14.75, 4.6, 0.95, "Filter hospitals", "keep matching speciality only", "code")
arrow((5.3, 14.75), (6.7, 14.75))
box(3.0, 16.2, 4.6, 0.95, "AHP weights (expert)", "staff, equipment, accreditation", "data")
box(9.0, 16.2, 4.6, 0.95, "AHP weights, TOPSIS rank", "transparent scoring", "code")
arrow((5.3, 16.2), (6.7, 16.2))
arrow((9.0, 15.225), (9.0, 15.725))
box(3.0, 17.65, 4.6, 0.95, "Write explanation", "from retrieved records only", "llm")
arrow((9.0, 16.675), (9.0, 17.0), (3.0, 17.0), (3.0, 17.175))
box(3.0, 19.1, 4.6, 0.95, "CGHS cost (display only)", "indicative, deferred", "data")
box(9.0, 19.1, 4.6, 0.95, "Result", "ranked list, reasons, sources", "code")
arrow((3.0, 18.125), (3.0, 18.4), (9.0, 18.4), (9.0, 18.625))
arrow((5.3, 19.1), (6.7, 19.1))

# ------------------------------------------------------------------ legend
for i, (kind, label) in enumerate([("llm", "LLM or embeddings"), ("code", "Deterministic code"),
                                   ("data", "Input or data")]):
    fill, edge, _, _ = STYLE[kind]
    x = 0.5 + i * 3.9
    parts.append(f'<rect x="{px(x)}" y="{px(20.45)}" width="22" height="22" rx="5" fill="{fill}" stroke="{edge}"/>')
    text(x + 0.42, 20.68, label, size=15, colour="#333333")


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
