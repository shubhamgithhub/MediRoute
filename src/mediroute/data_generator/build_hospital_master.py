#!/usr/bin/env python3
"""
Build evidence-backed hospital master rows for one or more cities.

Input : a candidates CSV per city (data/raw/data_generator/candidates/<city>.csv) with
        hospital_id, hospital_name, city, state, City_Tier, Hospital_Tier, hospital_type,
        ownership_type, nabh_query, branch_hint, official_source_url (optional)
        and the JCI list for the city produced by jci_scraper.py.
Output: an Excel workbook whose 'Master' sheet uses the team schema
        (same columns as the person sheets in Hosp_Data_Final.xlsx) plus evidence columns.

What is verified automatically, and how:
  nabh_status                  NABH directory name search (nabh_finder_scraper helpers);
                               only a hospital certificate (H-xxxx) for the right city/branch counts.
  jci_status                   JCI directory list for the city (jci_scraper.py output).
  official_source_url          must load; taken from the candidate file, else the NABH card's website.
  url_Internantional_patients  a link on the official site whose text/URL mentions "international".
  verified_specialties         specialty terms found on the official site, normalised with
                               data/medical_taxonomy/specialty_normalization.csv.
Fields that come from the candidate file (City_Tier, Hospital_Tier, hospital_type,
ownership_type) are judgement calls and are flagged as such in the notes column.

Usage:
  python -m mediroute.data_generator.build_hospital_master --candidates data/raw/data_generator/candidates/chennai.csv \
      --jci data/interim/jci/jci_chennai.csv --out data/interim/master/chennai_master.xlsx
"""
import argparse
import csv
import datetime as dt
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urljoin, urlparse

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from playwright.sync_api import sync_playwright

from mediroute.data_generator import nabh_finder_scraper as nabh
from mediroute.utils.paths import TAXONOMY_DIR

SCHEMA = ["hospital_id", "hospital_name", "city", "state", "City_Tier", "Hospital_Tier", "hospital_type",
          "ownership_type", "nabh_status", "jci_status", "verified_specialties",
          "international_patient_service", "official_source_url", "url_Internantional_patients",
          "verification_status", "evidence_quality_score", "cost_band_inr"]
EVIDENCE = ["nabh_certificate_no", "nabh_listed_name", "nabh_certificate_url", "nabh_match",
            "jci_ihco_id", "jci_listed_name", "website_status", "specialties_all_found",
            "data_collected_on", "notes"]
TAXONOMY = TAXONOMY_DIR / "specialty_normalization.csv"
MAX_SPECIALTIES = 6


# ---------------------------------------------------------------- specialties
def load_specialty_patterns():
    """raw website wording -> canonical specialty. Canonical names also match themselves."""
    pairs = {}
    with open(TAXONOMY, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            canon = (r.get("canonical_specialty") or "").strip()
            if canon:
                pairs[r["raw_specialty"].strip()] = canon
                pairs[canon] = canon
    # Common spellings the taxonomy does not list.
    extra = {"Orthopedics": "Orthopaedics", "Orthopaedic": "Orthopaedics", "Neurosurgery": "Neurosurgery",
             "Neurosciences": "Neurology", "Urology": "Urology", "Nephrology": "Nephrology",
             "Pulmonology": "Pulmonology", "Paediatrics": "Paediatrics", "Pediatrics": "Paediatrics",
             "Oncology": "Oncology", "Cardiology": "Cardiology", "Gastroenterology": "Gastroenterology",
             "Obstetrics": "Obstetrics & Gynaecology", "Gynaecology": "Obstetrics & Gynaecology",
             "Transplant": "Organ Transplant", "Critical Care": "Critical Care"}
    for raw, canon in extra.items():
        pairs.setdefault(raw, canon)
    # Longest phrases first so "Cardiac Surgery" wins over "Cardiac".
    return sorted(((re.compile(r"\b" + re.escape(raw).replace(r"\ ", r"\s+") + r"\b", re.I), canon)
                   for raw, canon in pairs.items()), key=lambda x: -len(x[0].pattern))


def find_specialties(text, patterns):
    counts = Counter()
    for rx, canon in patterns:
        n = len(rx.findall(text))
        if n:
            counts[canon] += n
            text = rx.sub(" ", text)  # don't double count the words of a longer phrase
    # Emergency/critical care appear in every site's menu; list them after the real specialties.
    generic = {"Emergency Medicine", "Critical Care"}
    ranked = [c for c, _ in counts.most_common()]
    return [c for c in ranked if c not in generic] + [c for c in ranked if c in generic]


# ---------------------------------------------------------------- website
# textContent, not innerText: specialty lists usually live in collapsed menus that innerText skips.
LINKS_JS = """() => [...document.querySelectorAll('a[href]')].map(a => [a.textContent.replace(/\\s+/g,' ').trim(), a.href])"""


def visit(page, url, timeout=45000):
    """Return (status_text, final_url, body_text, links)."""
    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        page.wait_for_timeout(2500)
        status = resp.status if resp else 0
        if status >= 400:
            return f"HTTP {status}", page.url, "", []
        links = page.evaluate(LINKS_JS)
        text = page.inner_text("body") + "\n" + "\n".join(t for t, _ in links)
        return "OK", page.url, text, links
    except Exception as e:
        return f"error: {type(e).__name__}", url, "", []


def same_site(a, b):
    host = lambda u: ".".join(urlparse(u).netloc.lower().split(".")[-2:])
    return host(a) == host(b)


def pick_link(links, base, word_groups):
    """First same-site link whose text or URL path (not the domain: 'miotinternational.com'
    is not an international-patients page) mentions a word. `word_groups` is tried in order,
    so specific phrases ('international patient') beat loose ones ('international')."""
    strip = lambda u: u.split("#")[0].split("?")[0].rstrip("/")
    for words in word_groups:
        for text, href in links:
            if not href.startswith("http") or not same_site(href, base) or strip(href) == strip(base):
                continue
            hay = (text + " " + urlparse(href).path.replace("-", " ").replace("_", " ")).lower()
            if any(w in hay for w in words):
                return href
    return ""


INTL_WORDS = [["international patient", "international patients", "internationalpatient", "/ipc"],
              ["nri", "overseas patient", "medical tourism", "global patient"]]
# (a bare "international" is too loose: on apollohospitals.com it matched
#  "Apollo Hospitals International Ltd, Ahmedabad". Give such pages via url_international.)
SPEC_WORDS = [["specialities", "specialties", "centres of excellence", "centers of excellence"],
              ["departments", "speciality", "specialty"]]


# ---------------------------------------------------------------- NABH / JCI
def nabh_lookup(page, cand, cache, delay_ms=2500):
    name_for_judge = cand["hospital_name"].split(",")[0]
    if cand.get("branch_hint"):
        name_for_judge += f" ({cand['branch_hint']})"
    terms = [cand["nabh_query"]] if cand.get("nabh_query") else nabh.search_terms(cand["hospital_name"])
    best = None
    for term in terms:
        if term not in cache:
            cards = []
            page.fill("#searchText", term)
            page.click("#searchHospitalBtn")
            page.wait_for_timeout(delay_ms + 2000)
            for _ in range(4):
                cards.extend(page.evaluate(nabh.CARD_JS))
                nxt = page.locator("#pagination li.page-item:not(.disabled) a", has_text="Next")
                if not nxt.count():
                    break
                nxt.first.click()
                page.wait_for_timeout(delay_ms + 1500)
            cache[term] = cards
        core = cand["hospital_name"].split(",")[0]
        branch = f" ({cand['branch_hint']})" if cand.get("branch_hint") else ""
        for c in cache[term]:
            # A card must share a distinctive word with the hospital name or query; otherwise
            # it is just another hospital in the same city (e.g. 'Iswarya' for 'Rajiv Gandhi').
            if not (nabh.tokens(core) | nabh.tokens(term)) & nabh.tokens(c["nabh_name"]):
                continue
            # Judge against the full name first (picks 'Medical Centre' over 'Hospital'),
            # then against the query, since NABH often lists a legal name ('MIOT Hospitals').
            full_score, full_v = nabh.judge_card(c, core + branch, cand["city"])
            term_score, term_v = nabh.judge_card(c, term + branch, cand["city"])
            verdict = "confident" if "confident" in (full_v, term_v) else (
                "review" if "review" in (full_v, term_v) else "other_city")
            if verdict == "other_city":
                continue
            rank = (verdict == "confident", full_score, term_score)
            if best is None or rank > best[0]:
                best = (rank, verdict, c)
    return (best[1], best[2]) if best else ("not_found", {})


def load_jci(path):
    if not path:
        print("WARNING: no --jci file given; every hospital will be marked 'Not listed' for JCI.")
        return []
    if not Path(path).exists():
        # Silently returning [] here once marked every hospital 'Not listed'.
        raise SystemExit(f"JCI file not found: {path}")
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def jci_lookup(cand, jci_rows):
    """Explicit `jci_name` in the candidate file wins (chains list several entries per city).
    Otherwise the distinctive query word must appear in the JCI name, so 'MGM Healthcare Malar'
    is not credited with 'MGM Healthcare Pvt. Ltd.' accreditation."""
    if cand.get("jci_name"):
        return next((r for r in jci_rows if r["Organization"].strip().lower() == cand["jci_name"].strip().lower()), None)
    want = nabh.tokens(cand["hospital_name"].split(",")[0]) | nabh.tokens(cand.get("nabh_query", ""))
    must = nabh.tokens(cand.get("nabh_query", ""))
    branch = (cand.get("branch_hint") or "").lower()
    best = None
    for r in jci_rows:
        got = nabh.tokens(r["Organization"])
        overlap = len(want & got) / max(len(want), 1)
        if overlap < 0.5 or (must and not must <= got):
            continue
        # A chain with several JCI entries in a city (e.g. Kauvery): prefer the one naming the branch,
        # and do not claim a branch-named entry for a different branch.
        org = r["Organization"].lower()
        names_branch = bool(branch) and branch.split()[0] in org
        rank = (names_branch, overlap)
        if best is None or rank > best[0]:
            best = (rank, r)
    return best[1] if best else None


# ---------------------------------------------------------------- main
def build_rows(cands, jci_rows, headed=False):
    patterns = load_specialty_patterns()
    today = dt.date.today().isoformat()
    rows = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed)
        nabh_page = browser.new_page(user_agent=nabh.UA)
        nabh_page.goto(nabh.URL, wait_until="load", timeout=60000)
        nabh_page.wait_for_timeout(2500)
        web = browser.new_context(user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                              "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")).new_page()
        cache = {}
        for cand in cands:
            notes = []
            verdict, card = nabh_lookup(nabh_page, cand, cache)
            if verdict == "confident":
                nabh_status = "Accredited" if card.get("status", "").lower() == "accredited" else card.get("status", "")
            elif verdict == "review":
                nabh_status = "Needs verification"
                notes.append(f"NABH: closest record in city is {card.get('certificate_no')} ({card.get('nabh_name','')[:60]}), "
                             "not a hospital certificate for this branch")
            else:
                nabh_status = "Not found in NABH directory"

            jci = jci_lookup(cand, jci_rows)
            jci_status = "Accredited" if jci else "Not listed"

            # Website: candidate file first, then the site listed on the JCI / NABH record.
            options = [("candidate", cand.get("official_source_url", "")),
                       ("JCI-listed", jci.get("Visit website", "") if jci else ""),
                       ("NABH-listed", card.get("website", ""))]
            site_status, final_url, text, links, url, tried = "no URL", "", "", [], "", []
            for label, u in options:
                if not u or u in [t[1] for t in tried]:
                    continue
                site_status, final_url, text, links = visit(web, u)
                tried.append((label, u, site_status))
                url = u
                if site_status == "OK":
                    if label != "candidate":
                        notes.append(f"website taken from {label} record")
                    break
            if site_status != "OK" and tried:
                notes.append("website unreachable: " + "; ".join(f"{u} ({s})" for _, u, s in tried))

            intl = ""
            if cand.get("url_international"):
                st, intl_final, _, _ = visit(web, cand["url_international"])
                if st == "OK":
                    intl = intl_final
                else:
                    notes.append(f"url_international {cand['url_international']} {st}")
            if not intl and links:
                intl = pick_link(links, final_url, INTL_WORDS)
            spec_page = pick_link(links, final_url, SPEC_WORDS) if links else ""
            if spec_page:
                _, _, spec_text, _ = visit(web, spec_page)
                text += "\n" + spec_text
            specs = find_specialties(text, patterns) if text else []

            strong = [verdict == "confident" or bool(jci), site_status == "OK", bool(specs)]
            quality = {3: "High", 2: "Medium"}.get(sum(strong), "Low")
            if verdict == "confident" and site_status == "OK":
                vstatus = "Verified"
            elif verdict == "confident" or jci:
                vstatus = "Partially verified"
            else:
                vstatus = "Needs verification"
            notes.append("Hospital_Tier/hospital_type/ownership_type from candidate list (manual judgement)")

            rows.append({
                "hospital_id": cand["hospital_id"], "hospital_name": cand["hospital_name"],
                "city": cand["city"], "state": cand["state"], "City_Tier": cand.get("City_Tier", ""),
                "Hospital_Tier": cand.get("Hospital_Tier", ""), "hospital_type": cand.get("hospital_type", ""),
                "ownership_type": cand.get("ownership_type", ""), "nabh_status": nabh_status,
                "jci_status": jci_status, "verified_specialties": "; ".join(specs[:MAX_SPECIALTIES]) or "NA",
                "international_patient_service": "Available" if intl else "Not found on website",
                "official_source_url": final_url if site_status == "OK" else url,
                "url_Internantional_patients": intl or "NA",
                "verification_status": vstatus, "evidence_quality_score": quality, "cost_band_inr": "NA",
                "nabh_certificate_no": card.get("certificate_no", ""), "nabh_listed_name": card.get("nabh_name", ""),
                "nabh_certificate_url": card.get("certificate_url", ""), "nabh_match": verdict,
                "jci_ihco_id": jci["IHCO ID"] if jci else "", "jci_listed_name": jci["Organization"] if jci else "",
                "website_status": site_status, "specialties_all_found": "; ".join(specs),
                "data_collected_on": today, "notes": " | ".join(notes),
            })
            r = rows[-1]
            print(f"{r['hospital_id']} {r['hospital_name'][:40]:40} NABH={r['nabh_status'][:12]:12} "
                  f"JCI={jci_status:10} site={site_status:8} intl={'Y' if intl else '-'} specs={len(specs)}")
        browser.close()
    return rows


def write_xlsx(rows, out):
    out.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Master"
    cols = SCHEMA + EVIDENCE
    ws.append(cols)
    head_fill, ev_fill = PatternFill("solid", fgColor="DDEBF7"), PatternFill("solid", fgColor="FFF2CC")
    for i, c in enumerate(ws[1], start=1):
        c.font = Font(bold=True)
        c.fill = head_fill if i <= len(SCHEMA) else ev_fill
    for r in rows:
        ws.append([r.get(c, "") for c in cols])
    for i, c in enumerate(cols, start=1):
        ws.column_dimensions[get_column_letter(i)].width = min(45, max(12, len(c) + 2))
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = ws.dimensions
    wb.save(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--jci", help="CSV written by jci_scraper.py for the same city")
    ap.add_argument("--out", required=True)
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    with open(args.candidates, newline="", encoding="utf-8-sig") as f:
        cands = list(csv.DictReader(f))
    rows = build_rows(cands, load_jci(args.jci), headed=args.headed)
    out = Path(args.out)
    write_xlsx(rows, out)
    with open(out.with_suffix(".csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=SCHEMA + EVIDENCE)
        w.writeheader()
        w.writerows(rows)
    print(f"Saved {len(rows)} rows -> {out} and {out.with_suffix('.csv')}")


if __name__ == "__main__":
    main()
