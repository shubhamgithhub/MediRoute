"""Draw the two README figures for Step 1 (HTML/SVG rendered to PNG with Playwright).

    PYTHONPATH=src .venv/Scripts/python.exe docs/evaluation/make_step1_figures.py

Numbers: Step 1 benchmark run 20261111_144211 (346 gold queries, llama3.2 on Ollama; judge
GPT-6 Luna via OpenRouter). See docs/evaluation/step1_benchmark_report.html.
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
ARCH = HERE.parent / "architecture"

SETS = ["core50 (n=50)", "mediroute (n=84)", "gretel, lay language (n=212)"]
SERIES = [  # name, colour, accuracy per set, confidently wrong per set
    ("Before: 3 voters, 2-of-3 majority", "#2a78d6", [80, 89, 54], [2, 2, 34]),
    ("Hybrid lookup + LLM, ask on disagreement", "#eb6834", [68, 67, 34], [2, 1, 7]),
    ("Hybrid lookup + LLM + guarded LLM judge", "#1baf7a", [82, 86, 77], [2, 4, 15]),
]
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
FONT = "Segoe UI, Arial, sans-serif"


def panel(x0: float, title: str, idx: int, vmax: int) -> str:
    w, h, top = 520, 300, 70
    group_w = w / len(SETS)
    bar_w = 34
    parts = [f'<text x="{x0}" y="{top - 30}" font-size="17" font-weight="600" fill="{INK}">{title}</text>']
    for t in range(0, vmax + 1, 20 if vmax > 50 else 10):
        y = top + h - h * t / vmax
        parts.append(f'<line x1="{x0}" x2="{x0 + w}" y1="{y}" y2="{y}" stroke="{GRID}" stroke-width="1"/>')
        parts.append(f'<text x="{x0 - 8}" y="{y + 4}" font-size="12" fill="{MUTED}" text-anchor="end">{t}%</text>')
    for g, label in enumerate(SETS):
        cx = x0 + group_w * g + group_w / 2
        start = cx - (len(SERIES) * bar_w + (len(SERIES) - 1) * 2) / 2
        for s, (_, colour, acc, wrong) in enumerate(SERIES):
            v = (acc, wrong)[idx][g]
            bh = h * v / vmax
            x = start + s * (bar_w + 2)
            y = top + h - bh
            r = min(4, bh / 2)
            parts.append(f'<path d="M{x},{top + h} V{y + r} Q{x},{y} {x + r},{y} H{x + bar_w - r} '
                         f'Q{x + bar_w},{y} {x + bar_w},{y + r} V{top + h} Z" fill="{colour}"/>')
            parts.append(f'<text x="{x + bar_w / 2}" y="{y - 6}" font-size="12.5" font-weight="600" fill="{INK}" '
                         f'text-anchor="middle">{v}%</text>')
        name, _, n = label.partition(" (")
        parts.append(f'<text x="{cx}" y="{top + h + 22}" font-size="13" fill="{INK}" text-anchor="middle">{name}</text>')
        parts.append(f'<text x="{cx}" y="{top + h + 39}" font-size="12" fill="{MUTED}" text-anchor="middle">({n}</text>')
    parts.append(f'<line x1="{x0}" x2="{x0 + w}" y1="{top + h}" y2="{top + h}" stroke="{MUTED}" stroke-width="1"/>')
    return "".join(parts)


def chart_svg() -> str:
    legend = []
    lx = 70
    for name, colour, _, _ in SERIES:
        legend.append(f'<rect x="{lx}" y="438" width="12" height="12" rx="2" fill="{colour}"/>'
                      f'<text x="{lx + 18}" y="449" font-size="13" fill="{INK}">{name}</text>')
        lx += 18 + len(name) * 7.0 + 28
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="470" font-family="{FONT}">'
            f'<rect width="1200" height="470" fill="{SURFACE}"/>'
            + panel(70, "Accuracy (higher is better)", 0, 100)
            + panel(660, "Confidently wrong (lower is better)", 1, 40)
            + "".join(legend) + "</svg>")


def box(x, y, w, h, title, sub, fill, stroke):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'
            f'<text x="{x + w / 2}" y="{y + 24}" font-size="14" font-weight="600" fill="{INK}" text-anchor="middle">{title}</text>'
            f'<text x="{x + w / 2}" y="{y + 43}" font-size="12" fill="{MUTED}" text-anchor="middle">{sub}</text>')


def arrow(x1, y1, x2, y2, label=""):
    mid = f'<text x="{(x1 + x2) / 2}" y="{min(y1, y2) - 6}" font-size="11.5" fill="{MUTED}" text-anchor="middle">{label}</text>' if label else ""
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2 - 7}" y2="{y2}" stroke="{MUTED}" stroke-width="1.6"/>'
            f'<path d="M{x2},{y2} l-9,-5 v10 z" fill="{MUTED}"/>' + mid)


def design_svg() -> str:
    code, llm, data = ("#e7f5ec", "#3a9a5b"), ("#eee8fb", "#7a5af5"), ("#eef0f1", "#8a8f8e")
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="430" font-family="{FONT}">',
         f'<rect width="1200" height="430" fill="{SURFACE}"/>',
         f'<text x="30" y="34" font-size="17" font-weight="600" fill="{INK}">Before (until 11 Nov): three voters, 2-of-3 majority</text>']
    y = 52
    p.append(box(30, y, 170, 58, "Patient text", "+ report, emergency rules", *data))
    p.append(arrow(200, y + 29, 250, y + 29))
    p.append(box(250, y, 190, 58, "LLM extracts evidence", "code keeps real phrases", *llm))
    p.append(arrow(440, y + 29, 500, y - 1 + 10))
    p.append(arrow(440, y + 29, 500, y + 29))
    p.append(arrow(440, y + 29, 500, y + 58))
    p.append(box(500, y - 18, 230, 34, "", "", *code)); p.append(f'<text x="615" y="{y + 4}" font-size="13" fill="{INK}" text-anchor="middle">V1 keyword search (lookup)</text>')
    p.append(box(500, y + 20, 230, 34, "", "", *code)); p.append(f'<text x="615" y="{y + 42}" font-size="13" fill="{INK}" text-anchor="middle">V2 meaning search (same lookup)</text>')
    p.append(box(500, y + 58, 230, 34, "", "", *llm)); p.append(f'<text x="615" y="{y + 80}" font-size="13" fill="{INK}" text-anchor="middle">V3 LLM picks 1 of 26</text>')
    p.append(arrow(730, y + 37, 790, y + 37))
    p.append(box(790, y + 8, 180, 58, "2 of 3 agree?", "yes → answer · no → ask", *code))
    p.append(f'<text x="990" y="{y + 30}" font-size="12" fill="{MUTED}">Risk: V1 and V2 share one dataset,</text>')
    p.append(f'<text x="990" y="{y + 47}" font-size="12" fill="{MUTED}">so their errors outvote a right LLM.</text>')

    y = 240
    p.append(f'<text x="30" y="{y - 26}" font-size="17" font-weight="600" fill="{INK}">Now in the app: lookup voter + LLM voter (better prompt), guarded LLM judge on disagreement</text>')
    p.append(box(30, y, 170, 58, "Patient text", "+ report, emergency rules", *data))
    p.append(arrow(200, y + 29, 250, y + 29))
    p.append(box(250, y, 190, 58, "LLM extracts evidence", "code keeps real phrases", *llm))
    p.append(arrow(440, y + 29, 500, y + 10))
    p.append(arrow(440, y + 29, 500, y + 52))
    p.append(box(500, y - 8, 230, 38, "", "", *code)); p.append(f'<text x="615" y="{y + 16}" font-size="13" fill="{INK}" text-anchor="middle">Hybrid lookup (keyword + meaning)</text>')
    p.append(box(500, y + 36, 230, 38, "", "", *llm)); p.append(f'<text x="615" y="{y + 60}" font-size="13" fill="{INK}" text-anchor="middle">LLM voter picks 1 of 26</text>')
    p.append(arrow(730, y + 33, 790, y + 33))
    p.append(box(790, y + 4, 150, 58, "Agree?", "yes → answer", *code))
    p.append(arrow(940, y + 33, 990, y + 33, "no"))
    p.append(box(990, y + 4, 190, 58, "LLM judge (GPT-6 Luna)", "picks from the 2 · cites evidence", *llm))
    p.append(f'<text x="790" y="{y + 92}" font-size="12" fill="{MUTED}">Judge guards: closed choice · evidence and quote checked by code</text>')
    p.append(f'<text x="790" y="{y + 109}" font-size="12" fill="{MUTED}">· asked twice with the order swapped. Any failed check,</text>')
    p.append(f'<text x="790" y="{y + 126}" font-size="12" fill="{MUTED}">"unclear" or error → ask the patient (as today).</text>')
    lx = 30
    for (fill, stroke), name in ((llm, "LLM / AI"), (code, "code / search"), (data, "input")):
        p.append(f'<rect x="{lx}" y="395" width="14" height="14" rx="3" fill="{fill}" stroke="{stroke}"/>'
                 f'<text x="{lx + 20}" y="407" font-size="12.5" fill="{INK}">{name}</text>')
        lx += 130
    p.append("</svg>")
    return "".join(p)


def render(svg: str, out: Path, width: int, height: int) -> None:
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=2)
        page.set_content(f"<html><body style='margin:0'>{svg}</body></html>")
        page.locator("svg").screenshot(path=str(out))
        browser.close()
    print("wrote", out)


if __name__ == "__main__":
    render(chart_svg(), HERE / "step1_benchmark_chart.png", 1200, 470)
    render(design_svg(), ARCH / "step1_design.png", 1200, 430)
