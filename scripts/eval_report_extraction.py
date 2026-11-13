"""Report-extraction metric: how many of a report's critical details does Step 1 pick up, and where are the rest lost?

    PYTHONPATH=src python scripts/eval_report_extraction.py

Step 1 is otherwise scored only on the final speciality. Here every readable synthetic report
(data/evaluation/synthetic_reports, cases R01-R15 and L01-L08) has a list of critical details
(data/evaluation/report_critical_details.csv: diagnosis / finding / procedure / body part; "decisive" =
the details the speciality depends on). Each detail is checked at three levels:

    A parser     is it in the text read from the PDF, and still there after the 6,000-character cut?
    B LLM        did the evidence LLM (prompt evidence_v1) return it?
    C kept       did it survive the code check and reach the evidence used by the voters and Step 2?

Also reported: unsupported phrases (not in the input; must be 0), extra phrases that are not a critical
detail (noise such as letterhead text), and whether the final speciality is right.

Runs the real Step 1 pipeline in this process (LLM from MEDIROUTE_LLM_PROVIDER / OPENROUTER key; set
MEDIROUTE_OPENROUTER_MODEL=openai/gpt-6-luna for the app's model). Its trace goes to the run folder, not
the admin page. Output: data/evaluation/results/<run>_report_extraction/ report.md, metrics.json, cases.jsonl
"""
from __future__ import annotations

import csv
import difflib
import json
import re
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from mediroute.backend.workflow.routing_nodes import MAX_REPORT_CHARS
from mediroute.specialty_routing.extraction.pdf_parser import PDFParser
from mediroute.specialty_routing.step1 import trace as step1_trace
from mediroute.specialty_routing.step1.evidence import _ABBREVIATIONS, _tokens
from mediroute.utils.paths import DATA_DIR, PROJECT_ROOT

ROOT = DATA_DIR / "evaluation" / "synthetic_reports"
DETAILS = DATA_DIR / "evaluation" / "report_critical_details.csv"
RESULTS = DATA_DIR / "evaluation" / "results"
MATCH_SHARE = 0.5  # a detail is captured when at least half of its words are covered by one phrase
SPACING_S = 12  # between cases: up to 4 LLM calls each, provider limit 20 requests per minute


# ------------------------------------------------------------------------------------- matching
def _compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _word_found(word: str, tokens: set[str]) -> bool:
    if word in tokens:
        return True
    full = _ABBREVIATIONS.get(word)
    if full and set(_tokens(full)) & tokens:
        return True
    if any(word in f.split() and a in tokens for a, f in _ABBREVIATIONS.items()):
        return True
    return len(word) >= 4 and bool(difflib.get_close_matches(word, tokens, n=1, cutoff=0.85))


def covered(detail: str, phrase: str) -> bool:
    """One phrase covers the detail: half of the detail's words found in it, or the same letters
    (handles text split by line breaks: "necro sis", "cardio myopathy")."""
    d, p = _compact(detail), _compact(phrase)
    if d and p and (d in p or (p in d and len(p) >= 0.5 * len(d))):
        return True
    words = _tokens(detail)
    if not words:
        return False
    tokens = set(_tokens(phrase))
    return sum(_word_found(w, tokens) for w in words) / len(words) >= MATCH_SHARE


def in_text(detail: str, text: str) -> bool:
    return covered(detail, text)


def captured(detail: str, phrases: list[str]) -> bool:
    return any(covered(detail, p) for p in phrases)


# ------------------------------------------------------------------------------------- run
def load_cases() -> list[dict]:
    details = defaultdict(list)
    for r in csv.DictReader(DETAILS.open(encoding="utf-8")):
        details[r["case_id"]].append({"detail": r["detail"], "type": r["type"], "decisive": r["decisive"] == "yes",
                                      "note": r["note"]})
    cases = []
    for r in csv.DictReader((ROOT / "manifest.csv").open(encoding="utf-8")):
        if r["case_id"] in details:
            ok = [s for s in [r["expected_specialty"], *r["acceptable_alternatives"].split(";")] if s]
            cases.append({**r, "ok": ok, "details": details[r["case_id"]],
                          "paths": [ROOT / f for f in r["files"].split(";") if f]})
    return cases


def trace_events(path: Path, request_id: str) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("request_id") == request_id:
            out.append(e)
    return out


def main() -> None:
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_report_extraction"
    out_dir = RESULTS / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    step1_trace.TRACE_FILE = out_dir / "trace.jsonl"  # keep these requests out of the admin page

    from mediroute.specialty_routing.step1.pipeline import Step1Input, Step1Pipeline
    pipeline = Step1Pipeline()
    model = getattr(pipeline.client, "model", "?")
    parser = PDFParser()
    rows = []
    for case in load_cases():
        files = [(p.name, p.read_bytes()) for p in case["paths"]]
        summary = parser.parse_multiple_pdfs(files)
        full_text = (summary.get("combined_text") or "").strip()
        report_text = full_text[:MAX_REPORT_CHARS]  # as the workflow does
        for attempt in range(3):  # the provider's per-minute limit (HTTP 429) must not count as a miss
            result = pipeline.analyze(Step1Input(text=case["typed_text"], report_text=report_text))
            events = trace_events(step1_trace.TRACE_FILE, result["request_id"])
            if not any(e.get("stage") == "llm_call" and not e.get("ok") for e in events):
                break
            print(f"{case['case_id']}: LLM call failed (rate limit?), waiting 65 s and retrying", flush=True)
            time.sleep(65)
        else:
            raise SystemExit(f"{case['case_id']}: LLM kept failing; run again later")
        llm = next((e for e in events if e.get("stage") == "llm_call" and e.get("stage_for") == "evidence_extraction"), {})
        ev = next((e for e in events if e.get("stage") == "evidence"), {})
        llm_phrases = [p for k in ("conditions", "procedures", "body_parts") for p in ((llm.get("parsed") or {}).get(k) or [])]
        kept = ev.get("kept") or {}
        kept_phrases = [p for k in ("conditions", "procedures", "body_parts", "keyword_matches") for p in kept.get(k, [])]
        source = f"{case['typed_text']}\n{report_text}"
        details = []
        for d in case["details"]:
            a_full, a_cut = in_text(d["detail"], full_text), in_text(d["detail"], report_text)
            b, c = captured(d["detail"], llm_phrases), captured(d["detail"], kept_phrases)
            lost_at = None if c else ("parser (not in text)" if not a_full else "6,000-character cut" if not a_cut
                                      else "LLM did not return it" if not b else "code check dropped it")
            details.append({**d, "A_in_text": a_full, "A_after_cut": a_cut, "B_llm": b, "C_kept": c, "lost_at": lost_at})
        extra = [p for p in kept_phrases if not any(covered(d["detail"], p) or covered(p, d["detail"]) for d in case["details"])]
        unsupported = [x for x in (ev.get("dropped") or [])]
        speciality = result.get("suggested_specialty")
        row = {"case_id": case["case_id"], "category": case["category"], "typed_text": case["typed_text"],
               "chars": len(full_text), "cut": len(full_text) > MAX_REPORT_CHARS,
               "expected": case["expected_specialty"], "decision": result["decision"], "speciality": speciality,
               "speciality_ok": bool(speciality and speciality in case["ok"]),
               "llm_output": llm.get("raw_response"), "llm_ms": llm.get("duration_ms"),
               "kept": kept, "llm_phrases": llm_phrases, "extra_kept": list(dict.fromkeys(extra)),
               "dropped_by_check": unsupported, "details": details, "request_id": result["request_id"]}
        rows.append(row)
        with (out_dir / "cases.jsonl").open("a", encoding="utf-8") as h:
            h.write(json.dumps(row, ensure_ascii=False) + "\n")
        got = sum(d["C_kept"] for d in details)
        print(f"{case['case_id']} {got}/{len(details)} kept · {row['decision']} → {speciality} "
              f"({'ok' if row['speciality_ok'] else 'expected ' + case['expected_specialty']})", flush=True)
        time.sleep(SPACING_S)

    metrics = summarise(rows, run_id, model)
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    report = render(metrics, rows)
    (out_dir / "report.md").write_text(report, encoding="utf-8")
    print("\n" + report + f"\nWritten to {out_dir.relative_to(PROJECT_ROOT)}")


# ------------------------------------------------------------------------------------- metrics
def share(items, key) -> float | None:
    items = list(items)
    return round(sum(bool(i[key]) for i in items) / len(items), 3) if items else None


def summarise(rows, run_id, model) -> dict:
    all_d = [d for r in rows for d in r["details"]]
    by_type = defaultdict(list)
    for d in all_d:
        by_type[d["type"]].append(d)
    lost = defaultdict(int)
    for d in all_d:
        if d["lost_at"]:
            lost[d["lost_at"]] += 1
    decisive_lost_cases = [r["case_id"] for r in rows if not any(d["C_kept"] for d in r["details"] if d["decisive"])]
    return {
        "run_id": run_id, "model": model, "cases": len(rows), "details": len(all_d),
        "match_rule": f"one phrase covers ≥ {MATCH_SHARE:.0%} of the detail's words (abbreviations and close "
                      "spellings count) or the same letters ignoring spaces",
        "levels": {k: share(all_d, k) for k in ("A_in_text", "A_after_cut", "B_llm", "C_kept")},
        "decisive": {k: share([d for d in all_d if d["decisive"]], k) for k in ("A_after_cut", "B_llm", "C_kept")},
        "by_type": {t: {"n": len(v), "C_kept": share(v, "C_kept"), "B_llm": share(v, "B_llm")} for t, v in sorted(by_type.items())},
        "lost_at": dict(lost),
        "cases_all_decisive_lost": decisive_lost_cases,
        "unsupported_phrases_kept": 0,  # by construction: the code check drops them; dropped ones listed per case
        "phrases_dropped_by_check": sum(len(r["dropped_by_check"]) for r in rows),
        "extra_phrases_kept": sum(len(r["extra_kept"]) for r in rows),
        "speciality_correct": share(rows, "speciality_ok"),
    }


def pct(x) -> str:
    return "–" if x is None else f"{x * 100:.0f}%"


def render(m, rows) -> str:
    L = [f"# Report-extraction metric {m['run_id']}", "",
         f"{m['cases']} readable synthetic reports · {m['details']} critical details · model {m['model']}", "",
         f"Match rule: {m['match_rule']}.", "",
         "## Where details survive", "",
         "| Level | All details | Decisive details |", "|---|---|---|",
         f"| A1 in the PDF text | {pct(m['levels']['A_in_text'])} | – |",
         f"| A2 still there after the 6,000-character cut | {pct(m['levels']['A_after_cut'])} | {pct(m['decisive']['A_after_cut'])} |",
         f"| B returned by the evidence LLM | {pct(m['levels']['B_llm'])} | {pct(m['decisive']['B_llm'])} |",
         f"| C kept after the code check (used by the voters and Step 2) | {pct(m['levels']['C_kept'])} | {pct(m['decisive']['C_kept'])} |",
         "", "## By type (kept, level C)", "", "| Type | Details | Kept | LLM returned |", "|---|---|---|---|"]
    L += [f"| {t} | {v['n']} | {pct(v['C_kept'])} | {pct(v['B_llm'])} |" for t, v in m["by_type"].items()]
    L += ["", "## Where the missing details were lost", ""]
    L += [f"- {k}: {v}" for k, v in sorted(m["lost_at"].items(), key=lambda kv: -kv[1])] or ["- none"]
    L += ["", f"Cases where every decisive detail was lost: {', '.join(m['cases_all_decisive_lost']) or 'none'}",
          f"Phrases dropped by the code check (not in the text): {m['phrases_dropped_by_check']} · "
          f"extra phrases kept that are not a critical detail: {m['extra_phrases_kept']} · "
          f"speciality correct: {pct(m['speciality_correct'])}", "",
          "## Per case", "", "| Case | Layout | Kept | Decisive kept | Missed | Extra phrases kept | Speciality |",
          "|---|---|---|---|---|---|---|"]
    for r in rows:
        ds = r["details"]
        dec = [d for d in ds if d["decisive"]]
        missed = "; ".join(f"{d['detail']} ({d['lost_at']})" for d in ds if not d["C_kept"]) or "–"
        L.append(f"| {r['case_id']} | {r['category']} | {sum(d['C_kept'] for d in ds)}/{len(ds)} | "
                 f"{sum(d['C_kept'] for d in dec)}/{len(dec)} | {missed} | {', '.join(r['extra_kept']) or '–'} | "
                 f"{r['speciality'] or r['decision']}{'' if r['speciality_ok'] else ' ✗'} |")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
