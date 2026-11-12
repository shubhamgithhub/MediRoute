"""Draft Step 2 capability grades (0-3) from the hospitals' own websites, for later human review.

Rubric (docs/design/step2_evaluation_design.md, section 5):
    3  the hospital's website confirms the speciality AND the procedure or condition
    2  speciality confirmed; procedure not confirmed (or the need has no procedure)
    1  related speciality only, or the speciality cannot be confirmed on the website
    0  cannot treat this need

Grades come from the WEBSITE, not from our CSV (the team-sheet procedures are what the systems rank
on; grading from them would score the systems against their own input). Steps:
  1. fetch each hospital's homepage and up to MAX_PAGES same-site pages relevant to its needs
     (robots.txt respected, one request per second per site, pages cached on disk)
  2. keep the sentences that mention the speciality or the procedure, each with its URL
  3. an LLM grader (a different model from the Step 2 capability judge) drafts the grade and must
     cite snippet ids; code checks them: a grade >= 2 without a valid citation is lowered to 1
  4. unreadable site: grade from the website-found specialities of our verification pipeline
     (max 2, confidence "low")
Every row is a DRAFT (grader column says so); review_grade overrides it after human review.

    PYTHONPATH=src .venv/Scripts/python.exe scripts/step2_draft_grades.py [--limit N] [--budget 0.45]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import sys
import time
import urllib.robotparser
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mediroute.utils.paths import DATA_DIR, HOSPITALS_FILE  # noqa: E402

EVAL = DATA_DIR / "evaluation"
TO_GRADE = EVAL / "step2_to_grade.csv"
GRADES = EVAL / "step2_capability_grades.csv"
SITE_CACHE = EVAL / "step2_site_cache"
GRADER_LOG = EVAL / "step2_grader_calls.jsonl"
GRADER_MODEL = "openai/gpt-5.6-luna"   # different from the capability judge (gpt-6-luna)
MAX_PAGES = 10
USER_AGENT = "Mozilla/5.0 (compatible; MediRoute-capstone-evaluation/1.0; academic research)"
COLUMNS = ["hospital_id", "hospital_name", "specialty", "procedure", "grade", "evidence_url", "evidence_note",
           "grader", "graded_on", "confidence", "review_grade", "reviewer"]

SPECIALTY_WORDS = {
    "Cardiology": ["cardio", "cardiac", "heart"], "Cardiothoracic Surgery": ["cardiothoracic", "cardiac surgery", "heart surgery", "cabg", "bypass", "ctvs"],
    "Pediatric Cardiology": ["paediatric cardi", "pediatric cardi", "congenital heart", "child heart"],
    "Oncology": ["oncology", "cancer", "tumour", "tumor", "chemotherapy", "radiation"],
    "Hematology & Bone Marrow Transplant": ["haematology", "hematology", "bone marrow", "bmt", "stem cell", "leukaemia", "leukemia"],
    "Orthopaedics": ["orthopaedic", "orthopedic", "joint replacement", "knee", "spine", "bone"],
    "Neurology": ["neurology", "neuro", "stroke", "epilepsy"], "Neurosurgery": ["neurosurgery", "neuro surgery", "brain surgery", "spine surgery", "brain tumour", "brain tumor"],
    "Gastroenterology": ["gastro", "liver", "hepatology", "digestive", "endoscopy"], "Nephrology": ["nephrology", "kidney", "renal", "dialysis"],
    "Urology": ["urology", "prostate", "urinary", "kidney stone"], "Organ Transplant": ["transplant"],
    "Obstetrics & Gynaecology": ["gynaecology", "gynecology", "obstetric", "women", "maternity"], "Reproductive Medicine": ["ivf", "fertility", "reproductive"],
    "Paediatrics": ["paediatric", "pediatric", "child", "neonat"], "Endocrinology": ["endocrin", "diabetes", "thyroid"],
    "Pulmonology": ["pulmonology", "pulmonary", "lung", "chest", "respiratory"], "Plastic & Reconstructive Surgery": ["plastic", "reconstructive", "cosmetic", "burn"],
    "Bariatric Surgery": ["bariatric", "weight loss", "obesity"], "Emergency Medicine": ["emergency", "trauma"], "Critical Care": ["critical care", "icu", "intensive care"],
    "Ophthalmology": ["ophthalm", "eye", "cataract"], "ENT": ["ent", "ear", "nose", "throat", "cochlear"], "Dermatology": ["dermatology", "skin"],
    "Psychiatry": ["psychiatry", "mental health"], "General Medicine": ["internal medicine", "general medicine"],
}
PROCEDURE_STOP = {"surgery", "treatment", "procedure", "the", "of", "for", "a", "and", "to", "my", "through", "with", "removal", "remove"}

GRADER_PROMPT = """You grade whether a hospital can treat a patient's need, for an evaluation data set.
Use ONLY the snippets from the hospital's own website below (and the list of specialities our website
check found). Do not use outside knowledge about the hospital.

Need: speciality "{specialty}"{procedure_text}

Grades:
3 = the website confirms the speciality AND this procedure (or the same procedure in other words,
    e.g. "bypass" = CABG, "valve replacement through a catheter" = TAVR / TAVI).
2 = the website confirms the speciality, but not this procedure{no_proc_note}.
1 = only a related speciality, or the speciality is not confirmed on the website.
0 = nothing suggests the hospital treats this need.

Specialities our website check found on {name}'s site: {found}

Website snippets (id, page, text):
{snippets}

Answer JSON: "grade" (0-3), "evidence" (snippet ids that support grades 2-3, e.g. ["S3"]),
"note" (one short sentence), "confidence" ("high" | "medium" | "low")."""

GRADER_SCHEMA = {"type": "object", "properties": {
    "grade": {"type": "integer", "enum": [0, 1, 2, 3]}, "evidence": {"type": "array", "items": {"type": "string"}},
    "note": {"type": "string"}, "confidence": {"type": "string", "enum": ["high", "medium", "low"]}},
    "required": ["grade", "evidence", "note", "confidence"]}


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.links, self._skip = [], [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"):
            self._skip += 1
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)
        if tag in ("p", "li", "h1", "h2", "h3", "h4", "br", "div", "td", "section"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def parse(page_html: str) -> tuple[str, list[str]]:
    p = _Text()
    try:
        p.feed(page_html)
    except Exception:
        pass
    text = re.sub(r"[ \t\r\f\v]+", " ", html.unescape("".join(p.parts)))
    return re.sub(r"\n\s*\n+", "\n", text).strip(), p.links


def need_words(specialty: str, procedure: str) -> list[str]:
    words = list(SPECIALTY_WORDS.get(specialty, [specialty.casefold()]))
    words += [w for w in re.findall(r"[a-z0-9]+", procedure.casefold()) if w not in PROCEDURE_STOP and len(w) > 2]
    extra = {"bypass": ["cabg"], "valve": ["tavr", "tavi"], "catheter": ["tavr", "tavi"], "stent": ["angioplasty", "pci"],
             "knee": ["arthroplasty"], "radiation": ["radiotherapy"], "prostate": ["prostatectomy"], "ivf": ["in vitro"],
             "weight": ["bariatric", "sleeve"], "hole": ["asd", "vsd", "septal"], "cyberknife": ["radiosurgery", "cyberknife"]}
    for w in list(words):
        words += extra.get(w, [])
    return list(dict.fromkeys(words))


# --------------------------------------------------------------------------- fetching
def fetch_site(hid: str, url: str, keywords: list[str]) -> dict:
    cache = SITE_CACHE / f"{hid}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    out = {"hospital_id": hid, "url": url, "pages": {}, "errors": []}
    if not url.startswith("http"):
        out["errors"].append("no website")
        cache.write_text(json.dumps(out), encoding="utf-8")
        return out
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    base = urlparse(url)
    robots = urllib.robotparser.RobotFileParser(f"{base.scheme}://{base.netloc}/robots.txt")
    try:
        robots.read()
    except Exception:
        robots = None

    def get(u: str) -> str | None:
        if robots is not None:
            try:
                if not robots.can_fetch(USER_AGENT, u):
                    out["errors"].append(f"robots.txt disallows {u}")
                    return None
            except Exception:
                pass
        try:
            r = session.get(u, timeout=15, allow_redirects=True)
            time.sleep(1.0)
            if r.status_code == 200 and "html" in r.headers.get("content-type", ""):
                return r.text
            out["errors"].append(f"{u}: HTTP {r.status_code}")
        except Exception as exc:
            out["errors"].append(f"{u}: {type(exc).__name__}")
        return None

    home = get(url)
    if home:
        text, links = parse(home)
        out["pages"][url] = text
        host = base.netloc.replace("www.", "")
        scored = {}
        for href in links:
            full = urljoin(url, href).split("#")[0]
            p = urlparse(full)
            if p.scheme not in ("http", "https") or host not in p.netloc or full in out["pages"]:
                continue
            if re.search(r"\.(pdf|jpg|png|jpeg|zip|docx?)$", p.path, re.I):
                continue
            path = (p.path + " " + p.query).casefold()
            score = sum(2 for k in keywords if k.replace(" ", "-") in path or k.replace(" ", "") in path)
            score += sum(1 for k in ("speciality", "specialty", "department", "centre", "center", "treatment", "procedure", "services")
                         if k in path)
            if score:
                scored[full] = max(score, scored.get(full, 0))
        for link in sorted(scored, key=lambda u: -scored[u])[:MAX_PAGES]:
            page = get(link)
            if page:
                out["pages"][link] = parse(page)[0]
    cache.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def snippets_for(site: dict, specialty: str, procedure: str, limit: int = 14) -> list[dict]:
    keys = need_words(specialty, procedure)
    proc_keys = [k for k in keys if k not in SPECIALTY_WORDS.get(specialty, [])]
    found, seen = [], set()
    for url, text in site.get("pages", {}).items():
        for sentence in re.split(r"(?<=[.!?])\s+|\n", text):
            s = sentence.strip()
            low = s.casefold()
            if len(s) < 15 or low in seen:
                continue
            hits = sum(1 for k in keys if k in low)
            if hits:
                seen.add(low)
                found.append((hits + 2 * sum(1 for k in proc_keys if k in low), url, s[:300]))
    found.sort(key=lambda x: -x[0])
    return [{"id": f"S{i}", "url": u, "text": t} for i, (_, u, t) in enumerate(found[:limit], 1)]


# --------------------------------------------------------------------------- grading
class Grader:
    MIN_GAP = 3.3

    def __init__(self, budget: float):
        from mediroute.specialty_routing.step1.ollama_client import OpenRouterClient
        self.client = OpenRouterClient(model=GRADER_MODEL)
        self.budget, self.spent, self._next = budget, 0.0, 0.0
        self.cache = {}
        if GRADER_LOG.exists():
            for line in GRADER_LOG.read_text(encoding="utf-8").splitlines():
                rec = json.loads(line)
                if rec.get("ok"):
                    self.cache[rec["key"]] = rec
                self.spent += rec.get("cost", 0) or 0

    def grade(self, prompt: str) -> dict:
        key = hashlib.sha256(f"{GRADER_MODEL}|{prompt}".encode()).hexdigest()[:20]
        if key in self.cache:
            return self.cache[key]
        if self.spent >= self.budget:
            return {"ok": False, "error": "budget reached"}
        for attempt in range(5):
            wait = self._next - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._next = time.monotonic() + self.MIN_GAP
            self.client._model_down.clear()
            self.client._down_reason = ""
            call = self.client.generate_json(prompt, GRADER_SCHEMA, purpose="step2_grading")
            if call.ok or "429" not in str(call.error):
                break
            time.sleep(15 * (attempt + 1))
        cost = float((call.details or {}).get("cost") or 0)
        self.spent += cost
        rec = {"key": key, "ok": call.ok, "parsed": call.parsed, "error": call.error, "cost": cost}
        with GRADER_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if call.ok:
            self.cache[key] = rec
        return rec


def fallback(h: dict, specialty: str, procedure: str, reason: str) -> dict:
    from mediroute.hospital_recommendation.specialty_filter import SpecialtyFilter
    on_site = SpecialtyFilter().specialty_evidence(h, specialty) == "website"
    grade = 2 if on_site else (1 if SpecialtyFilter().specialty_evidence(h, specialty) else 0)
    return {"grade": grade, "evidence_url": h.get("official_source_url", "") if on_site else "",
            "evidence_note": f"site not readable ({reason}); speciality {'found' if on_site else 'not found'} by the website check",
            "confidence": "low"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="grade only the first N pairs (test)")
    parser.add_argument("--budget", type=float, default=0.45)
    parser.add_argument("--workers", type=int, default=4, help="sites fetched in parallel (each site sequential)")
    args = parser.parse_args()
    SITE_CACHE.mkdir(parents=True, exist_ok=True)

    with TO_GRADE.open(encoding="utf-8-sig", newline="") as f:
        pairs = list(csv.DictReader(f))
    done = set()
    if GRADES.exists():
        with GRADES.open(encoding="utf-8-sig", newline="") as f:
            done = {(r["hospital_id"], r["specialty"], r["procedure"].casefold()) for r in csv.DictReader(f)}
    pairs = [p for p in pairs if (p["hospital_id"], p["specialty"], p["procedure"].casefold()) not in done]
    if args.limit:
        pairs = pairs[: args.limit]
    with HOSPITALS_FILE.open(encoding="utf-8-sig", newline="") as f:
        hospitals = {r["hospital_id"]: r for r in csv.DictReader(f)}

    by_h = defaultdict(list)
    for p in pairs:
        by_h[p["hospital_id"]].append(p)
    print(f"{len(pairs)} pairs to grade across {len(by_h)} hospitals", flush=True)

    def site_job(hid):
        kw = sorted({w for p in by_h[hid] for w in need_words(p["specialty"], p["procedure"])})
        return hid, fetch_site(hid, hospitals[hid].get("official_source_url", ""), kw)

    sites = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, (hid, site) in enumerate(pool.map(site_job, by_h), 1):
            sites[hid] = site
            if i % 10 == 0:
                print(f"fetched {i}/{len(by_h)} sites", flush=True)

    grader = Grader(args.budget)
    new_file = not GRADES.exists()
    with GRADES.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        if new_file:
            writer.writeheader()
        for n, p in enumerate(pairs, 1):
            h, site = hospitals[p["hospital_id"]], sites[p["hospital_id"]]
            snips = snippets_for(site, p["specialty"], p["procedure"])
            if not site.get("pages"):
                result = fallback(h, p["specialty"], p["procedure"], "; ".join(site.get("errors", [])[:1]) or "no pages")
            else:
                found = h.get("verified_specialties") or "none"
                prompt = GRADER_PROMPT.format(
                    specialty=p["specialty"],
                    procedure_text=f' and procedure "{p["procedure"]}"' if p["procedure"] else " (no procedure)",
                    no_proc_note="" if p["procedure"] else " (here: the need has no procedure, so 2 is the top grade "
                                                         "unless the website confirms the condition named by the patient)",
                    name=p["hospital_name"], found=found,
                    snippets="\n".join(f'{s["id"]} | {s["url"]} | {s["text"]}' for s in snips) or "(no matching text)")
                rec = grader.grade(prompt)
                if not rec.get("ok"):
                    result = fallback(h, p["specialty"], p["procedure"], f"grader: {rec.get('error')}")
                else:
                    g = rec["parsed"]
                    by_id = {s["id"]: s for s in snips}
                    cited = [by_id[c] for c in g.get("evidence", []) if c in by_id]
                    grade = int(g.get("grade", 0))
                    note = g.get("note", "")
                    if grade >= 2 and not cited and "website check" not in note.casefold():
                        if grade == 3 or not snips:  # guard: claims need a real snippet
                            note = f"[lowered from {grade}: no valid snippet cited] " + note
                            grade = 2 if (grade == 3 and found != "none" and p["specialty"] in found) else 1
                    result = {"grade": grade, "evidence_url": cited[0]["url"] if cited else "",
                              "evidence_note": (note + (f' | "{cited[0]["text"][:160]}"' if cited else ""))[:400],
                              "confidence": g.get("confidence", "medium")}
            writer.writerow({"hospital_id": p["hospital_id"], "hospital_name": p["hospital_name"],
                             "specialty": p["specialty"], "procedure": p["procedure"], **result,
                             "grader": f"DRAFT: LLM ({GRADER_MODEL}) from website snippets", "graded_on": str(date.today()),
                             "review_grade": "", "reviewer": ""})
            f.flush()
            if n % 25 == 0:
                print(f"graded {n}/{len(pairs)} · grader spend ${grader.spent:.3f}", flush=True)
    print(f"done · grader spend ${grader.spent:.3f}")


if __name__ == "__main__":
    main()
