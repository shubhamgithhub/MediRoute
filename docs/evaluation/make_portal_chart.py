"""Graph 2 for the team report: the real portal test, per gold set (correct / confidently wrong / asks).

    PYTHONPATH=src .venv/Scripts/python.exe docs/evaluation/make_portal_chart.py data/evaluation/portal_runs/<run>

One 100% bar per gold set; the three parts always add up to the set's request count.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import benchmark_step1 as bench  # noqa: E402

OUT = HERE / "step1_portal_chart.png"
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
FONT = "Segoe UI, Arial, sans-serif"
PARTS = [("correct", "Correct", "#1baf7a"), ("asks", "Asks the patient", "#e8a33d"),
         ("wrong", "Confidently wrong", "#d64541")]
SETS = [("core50", "core50 (team-written)"), ("mediroute", "mediroute (lay language)"),
        ("gretel", "gretel (symptoms only)"), ("all", "All requests")]


def counts(run: Path) -> dict[str, dict]:
    gold = {(s, g["query_id"]): g for s in ("core50", "mediroute", "gretel") for g in bench.load_gold(s)}
    out = {k: {"n": 0, "correct": 0, "asks": 0, "wrong": 0} for k, _ in SETS}
    for line in (run / "results.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        g = gold[(r["gold_set"], r["query_id"])]
        part = ("asks" if r["specialty"] is None else
                "correct" if r["specialty"] in {g["expected_specialty"], *g["alternatives"]} else "wrong")
        for key in (r["gold_set"], "all"):
            out[key]["n"] += 1
            out[key][part] += 1
    return out


def chart_svg(c: dict[str, dict], subtitle: str) -> str:
    x0, w, bar_h, gap, top = 250, 860, 38, 30, 96
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{top + len(SETS) * (bar_h + gap) + 60}" font-family="{FONT}">',
         f'<rect width="1200" height="100%" fill="{SURFACE}"/>',
         f'<text x="30" y="38" font-size="18" font-weight="600" fill="{INK}">Real portal test: what the patient got on the first message</text>',
         f'<text x="30" y="62" font-size="13" fill="{MUTED}">{subtitle}</text>']
    for t in range(0, 101, 20):
        x = x0 + w * t / 100
        p.append(f'<line x1="{x}" x2="{x}" y1="{top - 8}" y2="{top + len(SETS) * (bar_h + gap) - gap + 8}" stroke="{GRID}"/>')
        p.append(f'<text x="{x}" y="{top + len(SETS) * (bar_h + gap) + 6}" font-size="12" fill="{MUTED}" text-anchor="middle">{t}%</text>')
    for i, (key, label) in enumerate(SETS):
        s, y = c[key], top + i * (bar_h + gap)
        weight = "700" if key == "all" else "400"
        p.append(f'<text x="{x0 - 14}" y="{y + 17}" font-size="14" font-weight="{weight}" fill="{INK}" text-anchor="end">{label}</text>')
        p.append(f'<text x="{x0 - 14}" y="{y + 34}" font-size="12" fill="{MUTED}" text-anchor="end">n = {s["n"]}</text>')
        x, small = x0, []
        for part, name, colour in PARTS:
            share = s[part] / s["n"] if s["n"] else 0
            seg = w * share
            if seg > 0:
                p.append(f'<rect x="{x + 1}" y="{y}" width="{max(seg - 2, 1)}" height="{bar_h}" rx="3" fill="{colour}"/>')
                if seg > 64:
                    p.append(f'<text x="{x + seg / 2}" y="{y + 24}" font-size="13" font-weight="600" fill="#ffffff" '
                             f'text-anchor="middle">{share:.0%} ({s[part]})</text>')
                else:  # too narrow for a label inside: name it under the bar instead
                    small.append(f"{name.lower()} {share:.0%} ({s[part]})")
            x += seg
        if small:
            p.append(f'<text x="{x0 + w}" y="{y + bar_h + 15}" font-size="12" fill="{INK}" text-anchor="end">'
                     + " · ".join(small) + "</text>")
    ly = top + len(SETS) * (bar_h + gap) + 36
    lx = x0
    for _, name, colour in PARTS:
        p.append(f'<rect x="{lx}" y="{ly - 11}" width="13" height="13" rx="2" fill="{colour}"/>'
                 f'<text x="{lx + 19}" y="{ly}" font-size="13" fill="{INK}">{name}</text>')
        lx += 19 + len(name) * 7.4 + 34
    p.append("</svg>")
    return "".join(p)


def main() -> None:
    run = Path(sys.argv[1])
    meta = json.loads((run / "meta.json").read_text(encoding="utf-8"))
    c = counts(run)
    sub = (f"Run {run.name} · {c['all']['n']} requests through the running app (Step 1 → Step 2) · "
           f"GPT-6 Luna via OpenRouter, adopted design · started {meta['started'][:16].replace('T', ' ')}")
    svg = chart_svg(c, sub)
    height = int(svg.split('height="')[1].split('"')[0])
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": height}, device_scale_factor=2)
        page.set_content(f"<html><body style='margin:0'>{svg}</body></html>")
        page.locator("svg").screenshot(path=str(OUT))
        browser.close()
    print("wrote", OUT)
    print(json.dumps(c))


if __name__ == "__main__":
    main()
