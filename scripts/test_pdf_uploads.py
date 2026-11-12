"""Test the report upload with the synthetic PDFs (scripts/make_synthetic_reports.py), as the code is.

    PYTHONPATH=src python scripts/test_pdf_uploads.py [--spacing 12] [--no-ui]

Needs the running app (backend :8000, frontend :5500). Three levels:
  1 parser  every file through PDFParser: status, characters, whether the key finding survives the
            6,000-character cut the workflow applies
  2 API     every case POSTed to /api/patient-routing (real Step 1 + Step 2); checked against the
            manifest's expected outcome; the privacy case also checks the trace for phone / e-mail / ID
  3 screens a few cases uploaded through patient.html with Playwright (screenshots)
Writes data/evaluation/pdf_runs/<run>/results.jsonl and docs/evaluation/pdf_upload_report.html.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import time
from datetime import datetime
from pathlib import Path

import requests

from mediroute.backend.workflow.routing_nodes import MAX_REPORT_CHARS
from mediroute.specialty_routing.extraction.pdf_parser import PDFParser
from mediroute.utils.paths import DATA_DIR, LOG_DIR, PROJECT_ROOT

ROOT = DATA_DIR / "evaluation" / "synthetic_reports"
RUNS = DATA_DIR / "evaluation" / "pdf_runs"
REPORT = PROJECT_ROOT / "docs" / "evaluation" / "pdf_upload_report.html"
SHOTS = PROJECT_ROOT / "docs" / "evaluation" / "pdf_upload_screens"
API = "http://127.0.0.1:8000/api/patient-routing"
PAGE = "http://127.0.0.1:5500/patient.html"
KEY_FINDING = {"L04": "triple vessel", "R01": "triple vessel"}  # must survive the cut
PRIVATE = [r"\+91 98765 4\d{4}", r"[a-z]+\.test\d+@example\.com", r"1234 5678 9\d{3}"]
UI_CASES = ["R02", "L04", "E02", "E05", "E07"]
UNREADABLE_WORDS = re.compile(r"read|unreadable|ocr|scan|password|blank|clearer", re.I)


def manifest() -> list[dict]:
    rows = list(csv.DictReader((ROOT / "manifest.csv").open(encoding="utf-8")))
    for r in rows:
        r["paths"] = [ROOT / f for f in r["files"].split(";") if f]
        r["ok"] = [s for s in [r["expected_specialty"], *r["acceptable_alternatives"].split(";")] if s]
    return rows


# ------------------------------------------------------------------------------------- 1 parser
def parse_level(case: dict) -> dict:
    parser, files = PDFParser(), []
    for p in case["paths"]:
        try:
            d = parser.parse_pdf_bytes(p.read_bytes(), p.name)
            files.append({"file": p.name, "status": d["status"], "chars": d["text_length"], "text": d.get("text", "")})
        except Exception as exc:  # noqa: BLE001 - the finding is that it raises
            files.append({"file": p.name, "status": "EXCEPTION", "chars": 0, "text": "", "error": f"{type(exc).__name__}: {exc}"})
    combined = "\n\n".join(f["text"] for f in files if f["status"] == "success")
    out = {"files": [{k: v for k, v in f.items() if k != "text"} for f in files],
           "combined_chars": len(combined), "cut": len(combined) > MAX_REPORT_CHARS}
    key = KEY_FINDING.get(case["case_id"])
    if key:
        out["key_finding_in_text"] = key in combined.lower()
        out["key_finding_after_cut"] = key in combined[:MAX_REPORT_CHARS].lower()
    return out


# ------------------------------------------------------------------------------------- 2 API
def call_api(case: dict) -> dict:
    files = [("files", (p.name, p.read_bytes(), "application/pdf")) for p in case["paths"]]
    started = time.perf_counter()
    try:
        r = requests.post(API, data={"requirement": case["typed_text"], "top_k": "5"}, files=files, timeout=300)
        status, body = r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application/json") else {})
    except Exception as exc:  # noqa: BLE001
        status, body = 0, {"error": str(exc)}
    ms = int((time.perf_counter() - started) * 1000)
    step1 = body.get("step1") or {}
    rec = body.get("recommendation_result") or {}
    return {"http": status, "ms": ms, "detail": body.get("detail") or body.get("message"),
            "workflow_status": body.get("workflow_status"), "parse": body.get("parse_summary"),
            "decision": step1.get("decision"), "specialty": step1.get("suggested_specialty"),
            "evidence": step1.get("evidence"), "reason": step1.get("reason"), "notice": step1.get("notice"),
            "clarification_type": body.get("clarification_type"), "clarification_reason": body.get("clarification_reason"),
            "hospitals": len(rec.get("results") or []), "step1_request_id": step1.get("request_id")}


def privacy_check(request_id: str | None) -> dict:
    if not request_id:
        return {"checked": False}
    text = ""
    for line in (LOG_DIR / "step1_trace.jsonl").read_text(encoding="utf-8").splitlines()[-400:]:
        if request_id in line:
            text += line
    leaks = [p for p in PRIVATE if re.search(p, text)]
    return {"checked": True, "leaks": leaks}


def judge(case: dict, api: dict) -> tuple[str, str]:
    """(PASS | FAIL | CHECK, why) against the manifest's expected outcome."""
    want = case["expected_outcome"]
    told = any(UNREADABLE_WORDS.search(str(api.get(k) or "")) for k in ("detail", "clarification_reason", "notice", "reason"))
    parse = api.get("parse") or {}
    unreadable_files = (parse.get("needs_ocr_files") or 0) + (parse.get("error_files") or 0)
    # the screens show a notice for every file in parse_summary.unreadable_files (name + plain reason)
    told = told or bool(parse.get("unreadable_files"))
    if want == "api_error":
        ok = 400 <= api["http"] < 500 and bool(api.get("detail"))
        return ("PASS" if ok else "FAIL"), f"HTTP {api['http']}: {api.get('detail')}"
    if api["http"] != 200:
        return "FAIL", f"HTTP {api['http']}: {api.get('detail')}"
    if want == "route":
        if api["specialty"] in case["ok"]:
            return "PASS", f"{api['specialty']} ({api['decision']})"
        if api["specialty"] is None:
            return "FAIL", f"asked instead of answering: {api.get('clarification_reason') or api.get('reason')}"
        return "FAIL", f"wrong: {api['specialty']} (expected {case['expected_specialty']})"
    if want == "route_or_ask":
        if api["specialty"] in case["ok"] or api["specialty"] is None:
            return "PASS", f"{api['specialty'] or 'asked a question'} ({api['decision']})"
        return "FAIL", f"wrong: {api['specialty']}"
    if want == "unreadable_notice":
        if told:
            return "PASS", "patient told the file could not be read"
        return "FAIL", (f"{unreadable_files} unreadable file(s) but the patient is not told; result: "
                        f"{api['specialty'] or 'question'} ({api.get('clarification_reason') or api.get('reason')})")
    return "CHECK", "no rule"


# ------------------------------------------------------------------------------------- 3 screens
def ui_level(cases: list[dict]) -> dict[str, dict]:
    from playwright.sync_api import sync_playwright
    SHOTS.mkdir(parents=True, exist_ok=True)
    out = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for case in cases:
            page = browser.new_page(viewport={"width": 1366, "height": 768})
            page.goto(PAGE, wait_until="networkidle")
            page.evaluate("indexedDB.deleteDatabase('mediroute-prototype'); sessionStorage.clear()")
            page.reload(wait_until="networkidle")
            if case["typed_text"]:
                page.fill("#requirement", case["typed_text"])
            page.set_input_files("#medicalReports", [str(p) for p in case["paths"]])
            page.wait_for_timeout(800)
            page.check("#medical-disclaimer", force=True)
            shot = SHOTS / f"{case['case_id']}.png"
            state = "submit disabled"
            if page.locator("#analyze-button").is_enabled():
                page.click("#analyze-button")
                try:
                    page.wait_for_selector("#success-state:not([hidden]), #clarify-state:not([hidden]), "
                                           "#choice-state:not([hidden]), #form-error-summary:not([hidden])", timeout=120000)
                except Exception:  # noqa: BLE001
                    pass
                page.wait_for_timeout(800)
                for name in ("success", "clarify", "choice"):
                    if page.locator(f"#{name}-state").is_visible():
                        state = name
                if page.locator("#form-error-summary").is_visible():
                    state = "error: " + page.locator("#form-error-summary").inner_text()[:160]
            visible_errors = " | ".join(t for t in page.locator(".field-error").all_inner_texts() if t.strip())
            page.screenshot(path=str(shot), full_page=False)
            out[case["case_id"]] = {"state": state, "field_errors": visible_errors[:200],
                                    "shot": shot.relative_to(REPORT.parent).as_posix()}
            page.close()
            time.sleep(6)
        browser.close()
    return out


# ------------------------------------------------------------------------------------- report
def write_report(rows: list[dict], ui: dict, run: Path) -> None:
    e = lambda x: html.escape(str(x if x is not None else ""))  # noqa: E731
    n_pass = sum(r["verdict"] == "PASS" for r in rows)
    trs = []
    for r in rows:
        parse = ", ".join(f"{f['status']} ({f['chars']})" for f in r["parser"]["files"][:3])
        if len(r["parser"]["files"]) > 3:
            parse += f" … {len(r['parser']['files'])} files"
        extra = []
        if r["parser"].get("cut"):
            extra.append(f"text {r['parser']['combined_chars']} chars &gt; {MAX_REPORT_CHARS} cut; key finding after cut: "
                         f"{r['parser'].get('key_finding_after_cut')}")
        if r.get("privacy", {}).get("checked"):
            extra.append("privacy: " + ("LEAK " + ", ".join(r["privacy"]["leaks"]) if r["privacy"]["leaks"] else "no phone / e-mail / ID in the log"))
        cls = {"PASS": "pass", "FAIL": "fail"}.get(r["verdict"], "")
        trs.append(f"<tr class='{cls}'><td>{e(r['case_id'])}</td><td>{e(r['category'])}</td><td>{e(r['typed_text'][:60]) or '<i>none</i>'}</td>"
                   f"<td>{e(r['expected_specialty'] or r['expected_outcome'])}</td><td>{e(parse)}</td>"
                   f"<td><b>{e(r['verdict'])}</b> · {e(r['why'])}<br><span class='m'>{'<br>'.join(extra)}</span></td></tr>")
    shots = "".join(f"<figure><img src='{e(v['shot'])}'><figcaption><b>{e(k)}</b>: {e(v['state'])} {e(v['field_errors'])}</figcaption></figure>"
                    for k, v in ui.items())
    REPORT.write_text(f"""<!doctype html><html><head><meta charset="utf-8"><title>PDF upload test</title><style>
body{{font-family:Segoe UI,Arial,sans-serif;margin:24px;color:#1d2733;font-size:13px}} h1{{margin:0 0 4px}}
table{{border-collapse:collapse;width:100%}} td,th{{border-bottom:1px solid #e3e6ee;padding:5px 6px;vertical-align:top;text-align:left}}
th{{background:#eef0f7}} tr.pass td:first-child{{border-left:4px solid #2e9d63}} tr.fail td:first-child{{border-left:4px solid #c83a3a}}
.m{{color:#667;font-size:11.5px}} figure{{display:inline-block;width:48%;margin:6px 1%}} img{{width:100%;border:1px solid #ccd}}
</style></head><body>
<h1>Report upload test (code as is)</h1>
<p class="m">{datetime.now():%d %b %Y %H:%M} · {len(rows)} cases · synthetic text-based PDFs (data/evaluation/synthetic_reports) ·
run data/evaluation/pdf_runs/{run.name}. OCR for scanned or photographed reports is out of scope: such files are expected to be
reported as unreadable, not read.</p>
<h2>{n_pass} of {len(rows)} pass</h2>
<table><tr><th>Case</th><th>Kind</th><th>Typed text</th><th>Expected</th><th>Parser (chars)</th><th>Result through the API</th></tr>{''.join(trs)}</table>
<h2>Through the patient page</h2>{shots}
</body></html>""", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spacing", type=float, default=12.0, help="seconds between API cases (LLM rate limit)")
    ap.add_argument("--no-ui", action="store_true")
    args = ap.parse_args()
    run = RUNS / datetime.now().strftime("%Y%m%d_%H%M%S")
    run.mkdir(parents=True, exist_ok=True)
    rows = []
    cases = manifest()
    for i, case in enumerate(cases, 1):
        row = {k: case[k] for k in ("case_id", "category", "typed_text", "expected_specialty", "expected_outcome", "notes")}
        row["parser"] = parse_level(case)
        row["api"] = call_api(case)
        if case["case_id"] == "L06":
            row["privacy"] = privacy_check(row["api"].get("step1_request_id"))
        row["verdict"], row["why"] = judge(case, row["api"])
        rows.append(row)
        with (run / "results.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"[{i}/{len(cases)}] {case['case_id']} {row['verdict']}: {row['why'][:110]}", flush=True)
        if i < len(cases):
            time.sleep(args.spacing)
    ui = {} if args.no_ui else ui_level([c for c in cases if c["case_id"] in UI_CASES])
    (run / "ui.json").write_text(json.dumps(ui, indent=1), encoding="utf-8")
    write_report(rows, ui, run)
    print(f"{sum(r['verdict'] == 'PASS' for r in rows)}/{len(rows)} pass -> {REPORT.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
