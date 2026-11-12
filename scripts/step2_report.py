"""Step 2 benchmark report (HTML): end-to-end ranking metrics + a direct test of the three
capability methods (rules, embeddings, LLM) against the website-based grades.

    PYTHONPATH=src .venv/Scripts/python.exe scripts/step2_report.py [data/evaluation/results/<run>_step2]

Reads the latest eval_step2.py run (metrics.json, per_query.csv), step2_capability_grades.csv,
the LLM capability cache and the grader log. Writes docs/evaluation/step2_benchmark_report.html.
"""

from __future__ import annotations

import csv
import html
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mediroute.utils.paths import DATA_DIR, HOSPITALS_FILE, PROJECT_ROOT  # noqa: E402

EVAL = DATA_DIR / "evaluation"
OUT = PROJECT_ROOT / "docs" / "evaluation" / "step2_benchmark_report.html"
LABELS = {"B0": "Random among eligible", "B1": "Keyword search, no filters", "B2": "Filter, alphabetical",
          "B3": "Filter + rule bonuses", "B4": "Filter + semantic search", "ours": "Today's engine (filter + semantic + bonuses)",
          "A1": "Today's engine, website-confirmed only", "A2": "Today's engine, no procedure match",
          "S4": "v2: criteria + TOPSIS, capability by rules", "S5": "v2: criteria + TOPSIS, capability by embeddings",
          "S6": "v2: criteria + TOPSIS, capability by LLM judge", "S7": "v2: S6 + location tiers"}
ORDER = ["B0", "B1", "B2", "B3", "B4", "ours", "A1", "A2", "S4", "S5", "S6", "S7"]
AI = {"B0": "none", "B1": "none", "B2": "none", "B3": "none", "B4": "embeddings", "ours": "embeddings",
      "A1": "embeddings", "A2": "embeddings", "S4": "none", "S5": "embeddings", "S6": "LLM", "S7": "LLM"}


def capability_test():
    """Each method's verdict on every graded (hospital, need) pair that has a procedure, vs the grade."""
    from mediroute.hospital_recommendation.v2.capability import EXACT, RELATED, EmbeddingCapability, LLMCapability, RuleCapability
    with HOSPITALS_FILE.open(encoding="utf-8-sig", newline="") as f:
        hospitals = {r["hospital_id"]: r for r in csv.DictReader(f)}
    with (EVAL / "step2_capability_grades.csv").open(encoding="utf-8-sig", newline="") as f:
        grades = [r for r in csv.DictReader(f) if r["procedure"].strip()]
    methods = {"Rules": RuleCapability(), "Embeddings": EmbeddingCapability(),
               "LLM judge": LLMCapability(cache_file=EVAL / "step2_llm_capability_cache.jsonl", budget_usd=0.05)}
    out = {}
    for name, m in methods.items():
        tp = fp = fn = tn = unsafe = 0
        for g in grades:
            gold = int(g["review_grade"] or g["grade"])
            truth = gold == 3  # website confirms the procedure
            level = m.judge(g["procedure"], hospitals[g["hospital_id"]]).level
            claim = level in (EXACT, RELATED)
            tp += claim and truth
            fp += claim and not truth
            fn += (not claim) and truth
            tn += (not claim) and not truth
            unsafe += level == EXACT and gold <= 1
        n = tp + fp + fn + tn
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        out[name] = {"n": n, "precision": prec, "recall": rec, "f1": 2 * prec * rec / (prec + rec) if prec + rec else 0.0,
                     "accuracy": (tp + tn) / n if n else 0.0, "unsafe": unsafe, "claims": tp + fp}
    return out, len(grades)


def main() -> None:
    runs = sorted(EVAL.glob("results/*_step2"))
    run = Path(sys.argv[1]) if len(sys.argv) > 1 else runs[-1]
    metrics = json.loads((run / "metrics.json").read_text(encoding="utf-8"))
    with (EVAL / "step2_capability_grades.csv").open(encoding="utf-8-sig", newline="") as f:
        all_grades = list(csv.DictReader(f))
    conf = Counter(r["confidence"] for r in all_grades)
    dist = Counter(r["grade"] for r in all_grades)
    cache = [json.loads(l) for l in (EVAL / "step2_llm_capability_cache.jsonl").read_text(encoding="utf-8").splitlines()]
    grader = [json.loads(l) for l in (EVAL / "step2_grader_calls.jsonl").read_text(encoding="utf-8").splitlines()]
    cap_cost = sum(c.get("cost") or 0 for c in cache)
    grade_cost = sum(c.get("cost") or 0 for c in grader)
    cap_ms = [c["ms"] for c in cache if c.get("ms")]
    captest, n_cap = capability_test()

    e = html.escape
    systems = [s for s in ORDER if s in metrics["overall"]]
    ov = metrics["overall"]

    def cell(s, key, pct=False):
        v = ov[s][key]["mean"]
        if v is None:
            return "–"
        return f"{v:.0%}" if pct else f"{v:.2f}"

    best = max(systems, key=lambda s: ov[s]["NDCG@5"]["mean"] or 0)
    rows = ""
    for s in systems:
        ci = ov[s]["NDCG@5"]["ci95"]
        p = metrics.get("vs_ours_ndcg5_p", {}).get(s)
        rows += (f"<tr{' class=win' if s == best else ''}><td>{e(s)}</td><td>{e(LABELS[s])}</td><td>{AI[s]}</td>"
                 f"<td>{cell(s, 'NDCG@5')} <span class=m>[{ci[0]:.2f}–{ci[1]:.2f}]</span></td><td>{cell(s, 'P@5', True)}</td>"
                 f"<td>{cell(s, 'R@5', True)}</td><td>{cell(s, 'Hit@3', True)}</td><td>{cell(s, 'Capable@3', True)}</td>"
                 f"<td>{cell(s, 'Bad@3', True)}</td><td>{'–' if p is None else f'{p:.3f}'}</td></tr>")
    strata_rows = ""
    for stratum, by in metrics["by_stratum"].items():
        cells = []
        for s in systems:
            value = by[s]["NDCG@5"]
            cells.append(f"<td>{'–' if value is None else format(value, '.2f')}</td>")
        strata_rows += f"<tr><td>{e(stratum)}</td>" + "".join(cells) + "</tr>"
    cap_rows = "".join(
        f"<tr><td>{e(k)}</td><td>{v['precision']:.0%}</td><td>{v['recall']:.0%}</td><td>{v['f1']:.2f}</td>"
        f"<td>{v['accuracy']:.0%}</td><td>{v['unsafe']}</td></tr>" for k, v in captest.items())

    s4, s5, s6 = (ov.get(x, {}).get("NDCG@5", {}).get("mean") for x in ("S4", "S5", "S6"))
    margin = None if None in (s4, s5, s6) else s6 - max(s4, s5)
    if margin is None:
        verdict = "Not all v2 systems ran."
    elif margin >= 0.05:
        verdict = f"<b>The LLM earns its place</b>: S6 beats the best non-LLM capability method by {margin:+.2f} NDCG@5 (rule: ≥ +0.05)."
    else:
        verdict = (f"<b>The LLM does not clearly earn its place here</b>: S6 vs best non-LLM {margin:+.2f} NDCG@5 "
                   "(rule: ≥ +0.05). Use the cheaper method unless the capability test below shows a safety gain.")

    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Step 2 Benchmark</title><style>
:root {{ --bg:#f7f8f6; --card:#fff; --fg:#1b2321; --muted:#5d6b68; --line:#d8e0de; --head:#e6f0ee; --good-bg:#e3f3e8; --warn-bg:#fbf1db; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#121716; --card:#1b2321; --fg:#e4ebe9; --muted:#9aaba7; --line:#2f3b39; --head:#1f3330; --good-bg:#17331f; --warn-bg:#3a2e14; color-scheme:dark; }} }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:15px/1.55 "Segoe UI",system-ui,Arial,sans-serif; padding:28px max(16px,3vw) 56px; }}
main {{ max-width:1100px; margin:0 auto; display:flex; flex-direction:column; gap:20px; }}
h1 {{ margin:0; font-size:1.7rem; }} h2 {{ margin:0 0 6px; font-size:1.15rem; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:16px 18px; }}
.scroll {{ overflow-x:auto; }} table {{ width:100%; border-collapse:collapse; font-size:.9rem; font-variant-numeric:tabular-nums; }}
th, td {{ padding:7px 9px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
th {{ background:var(--head); font-size:.82rem; }} tr.win td {{ background:var(--good-bg); font-weight:600; }}
.m, .muted {{ color:var(--muted); font-size:.85rem; font-weight:400; }} .verdict {{ background:var(--warn-bg); padding:10px 14px; border-radius:8px; }}
code {{ font-family:Consolas,monospace; font-size:.85em; }}
</style></head><body><main>
<header><h1>Step 2 benchmark: today's engine vs design v2</h1>
<p class="muted">Run {e(metrics['run_id'])} · {metrics['queries']} gold requests (5 strata) · oracle mode (the gold speciality and procedure go straight to Step 2) ·
grades are <b>drafts</b> from the hospitals' own websites, awaiting a human check of a sample.</p></header>

<section class="card"><h2>Verdict: does the LLM add value in Step 2?</h2><p class="verdict">{verdict}</p></section>

<section class="card"><h2>1. End-to-end ranking (all {metrics['queries']} requests)</h2><div class="scroll"><table>
<tr><th>ID</th><th>System</th><th>AI used</th><th>NDCG@5 (95% CI)</th><th>P@5</th><th>R@5</th><th>Hit@3</th><th>Capable@3</th><th>Bad@3</th><th>p vs today</th></tr>
{rows}</table></div>
<p class="muted">NDCG@5 = ranking quality of the top 5 with graded relevance (headline). P@5 / R@5 = relevant (grade ≥ 2) among the top 5 / of all relevant.
Hit@3 = a relevant hospital in the top 3. Capable@3 = a capable hospital in the top 3 <i>wherever it is</i> (shows location tiers). Bad@3 = a top-3 hospital that cannot treat the need (safety).
Relevance counts a hospital outside the patient's area as 0, so S7's widened results score only in Capable@3. p = paired permutation test of NDCG@5 against today's engine.</p></section>

<section class="card"><h2>2. NDCG@5 by stratum</h2><div class="scroll"><table>
<tr><th>Stratum</th>{''.join(f'<th>{s}</th>' for s in systems)}</tr>{strata_rows}</table></div>
<p class="muted">S1 big area, speciality only · S2 big area + procedure · S3 state / anywhere + procedure · S4 small city · S5 edge cases.</p></section>

<section class="card"><h2>3. Capability test: can this hospital do the procedure the patient mentioned?</h2><div class="scroll"><table>
<tr><th>Method</th><th>Precision</th><th>Recall</th><th>F1</th><th>Accuracy</th><th>Unsafe claims</th></tr>{cap_rows}</table></div>
<p class="muted">{n_cap} graded (hospital, procedure) pairs. Truth = the website confirms the procedure (grade 3). A method "claims" capability when it says exact or related.
Unsafe = says exact although the website grade is 0–1. The methods read our hospital data; the grades come from the websites, so this also measures how far our data can be trusted.</p></section>

<section class="card"><h2>4. Grades, cost and limits</h2><div class="scroll"><table>
<tr><th>Item</th><th>Value</th></tr>
<tr><td>Graded pairs</td><td>{len(all_grades)} · grades {', '.join(f'{k}: {v}' for k, v in sorted(dist.items()))}</td></tr>
<tr><td>Grade confidence</td><td>{', '.join(f'{k}: {v}' for k, v in conf.most_common())} (low = site not readable, graded from our website check)</td></tr>
<tr><td>LLM capability judge (GPT-6 Luna)</td><td>{len(cache)} calls · ${cap_cost:.3f} · median {statistics.median(cap_ms) / 1000 if cap_ms else 0:.1f} s per call</td></tr>
<tr><td>LLM grader (GPT-5.6 Luna, different model)</td><td>{len(grader)} calls · ${grade_cost:.3f}</td></tr>
<tr><td>Total LLM spend</td><td>${cap_cost + grade_cost:.3f} (cap $1)</td></tr>
</table></div>
<ul class="muted"><li>Grades are LLM drafts from website snippets; a person must check a sample (design: 20% + all grade-3s, kappa ≥ 0.6) before the numbers are final.</li>
<li>Some hospital sites block automated reading (robots.txt) or render with JavaScript; those pairs were graded from our earlier website check (confidence "low").</li>
<li>About 45 requests: NDCG differences under ~0.05 may not be significant; see the confidence intervals and p-values.</li>
<li>Embedding thresholds (0.70 / 0.50) and TOPSIS weights (paper's experts) were fixed before the run, not tuned on these grades.</li></ul></section>
<p class="muted">Code: <code>src/mediroute/hospital_recommendation/v2/</code> · <code>scripts/eval_step2.py</code> (systems S4–S7) · <code>scripts/step2_draft_grades.py</code> · <code>scripts/step2_report.py</code> · design: <code>docs/design/step2_design_v2.html</code></p>
</main></body></html>"""
    OUT.write_text(doc, encoding="utf-8")
    print(f"report: {OUT}")


if __name__ == "__main__":
    main()
