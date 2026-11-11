#!/usr/bin/env python3
"""
Collect results from the NABH "Find an Accredited Healthcare Organisation" page.

STATUS: written without being able to run it against the live site (nabh.co is not
reachable from the sandbox it was written in). Run with --debug first, look at
data/interim/<city>/network_log.json and page.html, then adjust SELECTORS below if needed.

Setup:
    pip install playwright
    playwright install chromium

Examples:
    python -m mediroute.data_generator.nabh_finder_scraper --debug --cities Chennai
    python -m mediroute.data_generator.nabh_finder_scraper --cities Chennai Kolkata Ahmedabad Kochi --names MGM MIOT Kauvery
    python -m mediroute.data_generator.nabh_finder_scraper --cities Chennai --headed --delay 3

Please read https://nabh.co/terms-and-conditions/ before running, keep the delay
polite, and use the data only for the project. One browser, one city at a time.
"""
import argparse
import csv
import json
import pathlib
import re
import sys
from urllib import robotparser

from playwright.sync_api import sync_playwright

from mediroute.utils.paths import PROCESSED_DATA_DIR

URL = "https://nabh.co/find-a-healthcare-organisation/"
UA = "Mozilla/5.0 (student project; contact: mepravintpatil@gmail.com)"
CITY_STATE = {
    "Chennai": "Tamil Nadu",
    "Kolkata": "West Bengal",
    "Ahmedabad": "Gujarat",
    "Kochi": "Kerala",
}

# Adjust these after the first --debug run if the page uses custom widgets.
SELECTORS = {
    "state_select_index": 0,   # position of the state <select> on the page
    "city_select_index": 1,    # position of the city <select> on the page
    "search_button_text": r"^\s*search\s*$",
    "more_button_text": r"(show|load|view)\s*more|next",
    "card_selector": None,     # e.g. ".result-card" if you want a DOM fallback
}


def robots_allows():
    rp = robotparser.RobotFileParser("https://nabh.co/robots.txt")
    try:
        rp.read()
        return rp.can_fetch("*", URL)
    except Exception:
        print("Warning: could not read robots.txt; check it manually.", file=sys.stderr)
        return True


def choose(page, index, wanted, delay_ms):
    """Pick an option containing `wanted`. Works for <select>; falls back to click-and-pick."""
    sel = page.locator("select").nth(index)
    try:
        for _ in range(20):  # options may load after the previous choice
            labels = sel.locator("option").all_inner_texts()
            match = next((l for l in labels if wanted.lower() in l.strip().lower()), None)
            if match:
                sel.select_option(label=match)
                page.wait_for_timeout(delay_ms)
                return
            page.wait_for_timeout(500)
        raise RuntimeError(f"option '{wanted}' not found in select #{index}: {labels[:10]}")
    except Exception:
        # custom dropdown fallback
        page.get_by_text(re.compile(r"select (state|city)", re.I)).nth(0 if index == 0 else 1).click()
        page.get_by_text(wanted, exact=False).first.click()
        page.wait_for_timeout(delay_ms)


def find_record_list(obj):
    """Return the largest list of dicts found anywhere inside a JSON structure."""
    best = []
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, list):
            if cur and all(isinstance(x, dict) for x in cur) and len(cur) > len(best):
                best = cur
            stack.extend(cur)
        elif isinstance(cur, dict):
            stack.extend(cur.values())
    return best


def flatten(rec, prefix=""):
    out = {}
    for k, v in rec.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(flatten(v, key + "."))
        elif isinstance(v, list):
            out[key] = "; ".join(json.dumps(x, ensure_ascii=False) if isinstance(x, (dict, list)) else str(x) for x in v)
        else:
            out[key] = v
    return out


def run_city(pw, city, args, outdir):
    state = CITY_STATE.get(city, args.state or "")
    folder = outdir / city.lower()
    folder.mkdir(parents=True, exist_ok=True)
    browser = pw.chromium.launch(headless=not args.headed)
    ctx = browser.new_context(user_agent="Mozilla/5.0 (student project; contact: mepravintpatil@gmail.com)")
    page = ctx.new_page()

    log, captured = [], []

    def safe_post(req):
        # post_data raises on binary bodies (e.g. analytics beacons); keep the log going.
        try:
            return req.post_data
        except Exception:
            return "<binary>"

    def on_request(req):
        log.append({"method": req.method, "url": req.url, "type": req.resource_type, "post": safe_post(req)})

    def on_response(resp):
        try:
            if resp.request.resource_type in ("xhr", "fetch") and "json" in resp.headers.get("content-type", ""):
                captured.append({"url": resp.url, "status": resp.status,
                                 "post": safe_post(resp.request), "json": resp.json()})
        except Exception:
            pass

    page.on("request", on_request)
    page.on("response", on_response)

    page.goto(URL, wait_until="networkidle")
    page.wait_for_timeout(int(args.delay * 1000))

    choose(page, SELECTORS["state_select_index"], state, int(args.delay * 1000))
    choose(page, SELECTORS["city_select_index"], city, int(args.delay * 1000))
    page.get_by_role("button", name=re.compile(SELECTORS["search_button_text"], re.I)).first.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(int(args.delay * 1000))

    # Expand paginated or "load more" results.
    for _ in range(args.max_rounds):
        btn = page.get_by_role("button", name=re.compile(SELECTORS["more_button_text"], re.I))
        link = page.get_by_role("link", name=re.compile(SELECTORS["more_button_text"], re.I))
        target = btn if btn.count() else link
        if not target.count() or not target.first.is_visible():
            break
        target.first.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(int(args.delay * 1000))

    # Always keep raw evidence so selectors/endpoints can be corrected.
    (folder / "network_log.json").write_text(json.dumps(log, indent=1, ensure_ascii=False))
    (folder / "captured_json.json").write_text(json.dumps(captured, indent=1, ensure_ascii=False))
    if args.debug:
        (folder / "page.html").write_text(page.content())
        page.screenshot(path=str(folder / "page.png"), full_page=True)

    # Preferred route: records from the JSON the page itself loaded.
    records = []
    for item in captured:
        records.extend(find_record_list(item["json"]))
    rows = [flatten(r) for r in records]

    # Fallback: visible result cards, if a selector was provided.
    if not rows and SELECTORS["card_selector"]:
        for card in page.locator(SELECTORS["card_selector"]).all():
            rows.append({"raw_text": " | ".join(t.strip() for t in card.inner_text().splitlines() if t.strip())})

    if args.names:
        wanted = [n.lower() for n in args.names]
        rows = [r for r in rows if any(w in json.dumps(r, ensure_ascii=False).lower() for w in wanted)]

    for r in rows:
        r["_queried_city"], r["_queried_state"] = city, state

    if rows:
        cols = sorted({k for r in rows for k in r})
        with open(folder / f"{city.lower()}_nabh.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
    print(f"{city}: {len(rows)} records, {len(captured)} JSON responses captured -> {folder}")
    browser.close()
    return rows


# ---------------------------------------------------------------------------
# Name-search mode: look up each hospital in data/processed/hospitals_master.csv using the
# page's own "Search by name" box, then pick the best card for the hospital's city.
# ---------------------------------------------------------------------------
CITY_ALIASES = {
    "bengaluru": ["bengaluru", "bangalore"],
    "gurugram": ["gurugram", "gurgaon"],
    "new delhi": ["delhi"],
    "mumbai": ["mumbai", "bombay", "navi mumbai"],
    "chennai": ["chennai", "madras"],
    "hyderabad": ["hyderabad", "secunderabad", "rangareddy", "ranga reddy"],
    "kolkata": ["kolkata", "calcutta", "howrah"],
    "kochi": ["kochi", "cochin", "ernakulam", "aluva"],
    "visakhapatnam": ["visakhapatnam", "vizag"],
    "chandigarh": ["chandigarh", "mohali", "sas nagar", "panchkula"],
    "ahmedabad": ["ahmedabad", "gandhinagar"],
    "navi mumbai": ["navi mumbai", "vashi", "thane"],
}
STOPWORDS = {"hospital", "hospitals", "the", "and", "&", "of", "pvt", "ltd", "limited",
             "centre", "center", "research", "super", "speciality", "specialty", "-", "a", "unit"}


def tokens(text):
    # len > 1: apostrophes split "Nizam's" / "Children's" into a lone "s", which once made
    # NIMS match an unrelated children's hospital.
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS and len(t) > 1}


def city_terms(city):
    base = re.sub(r"\(.*?\)", "", city).strip().lower()
    return CITY_ALIASES.get(base, [base])


def search_term(name):
    """'Apollo Hospitals (Greams Road)' -> 'Apollo Hospitals'; 'Medanta - The Medicity' -> 'Medanta'."""
    core = re.sub(r"\(.*?\)", "", name)
    core = re.split(r"\s[-–,]\s|,", core)[0]
    return core.strip()


def search_terms(name):
    """Full core name first, then its most distinctive single word as a fallback
    (NABH often lists a legal/short name, e.g. 'MIOT Hospitals' for 'MIOT International')."""
    core = search_term(name)
    generic = STOPWORDS | {"international", "national", "global", "health", "city", "healthcare",
                           "apollo", "fortis", "max", "manipal", "care", "heart", "institute"}
    words = [w for w in re.findall(r"[A-Za-z]+", core) if len(w) > 2 and w.lower() not in generic]
    terms = [core] + ([max(words, key=len)] if words else [])
    return list(dict.fromkeys(terms))


def branch_tokens(name):
    """Words inside parentheses identify the branch: '(HAL Airport Rd)' -> {'hal', 'airport'}."""
    inner = " ".join(re.findall(r"\((.*?)\)", name)).lower().replace(" rd", " road")
    return {t for t in re.findall(r"[a-z]+", inner) if t not in {"road", "rd"}}


CARD_JS = """() => [...document.querySelectorAll('.organisation-list')].map(c => {
    const t = s => (c.querySelector(s)?.innerText || '').replace(/\\s+/g, ' ').trim();
    const link = c.querySelector('.hs-col-1 a, .hs-col-4 a');
    const web = [...c.querySelectorAll('a')].find(a => /visit website/i.test(a.innerText));
    return {nabh_name: t('.hs-col-1'), address: t('.hs-col-2'), certificate_no: t('.hs-col-4'),
            status: t('.certification-icon'), certificate_url: link ? link.href : '',
            website: web ? web.href : ''};
})"""


def judge_card(card, name, city):
    """Return (score, verdict). Only a hospital-programme certificate (H-xxxx) in the right
    city, with the right branch when one is named, counts as 'confident'. Blood banks (BB-),
    ethics committees (EC-), labs etc. of the same hospital are not hospital accreditation."""
    want, got = tokens(search_term(name)), tokens(card["nabh_name"])
    name_score = len(want & got) / max(len(want), 1)
    hay = (card["nabh_name"] + " " + card["address"]).lower()
    city_ok = any(c in hay for c in city_terms(city))
    hco = card["certificate_no"].upper().startswith("H-")
    branch = branch_tokens(name)
    branch_ok = not branch or any(b in hay for b in branch)
    score = round(name_score + city_ok + 0.5 * hco + 0.5 * (bool(branch) and branch_ok), 3)
    if city_ok and hco and branch_ok and name_score >= 0.5:
        return score, "confident"
    return score, "review" if city_ok else "other_city"


def run_master(pw, args, outdir):
    with open(args.master, newline="", encoding="utf-8-sig") as f:
        hospitals = list(csv.DictReader(f))
    browser = pw.chromium.launch(headless=not args.headed)
    page = browser.new_page(user_agent=UA)
    page.goto(URL, wait_until="load", timeout=60000)
    page.wait_for_timeout(int(args.delay * 1000))

    def search(term):
        if term in cache:
            return cache[term]
        cards = []
        page.fill("#searchText", term)
        page.click("#searchHospitalBtn")
        page.wait_for_timeout(int(args.delay * 1000) + 2000)
        for _ in range(args.max_pages):
            cards.extend(page.evaluate(CARD_JS))
            nxt = page.locator("#pagination li.page-item:not(.disabled) a", has_text="Next")
            if not nxt.count():
                break
            nxt.first.click()
            page.wait_for_timeout(int(args.delay * 1000) + 1500)
        cache[term] = cards
        print(f"  '{term}': {len(cards)} NABH records")
        return cards

    rank = {"confident": 2, "review": 1, "other_city": 0}
    rows, cache = [], {}
    for h in hospitals:
        best, used = None, ""
        for term in search_terms(h["name"]):
            for c in search(term):
                score, verdict = judge_card(c, h["name"], h["city"])
                key = (rank[verdict], score)
                if best is None or key > best[0]:
                    best, used = (key, verdict, score, c), term
            if best and best[1] == "confident":
                break  # no need for the fallback term
        _, verdict, score, card = best if best else (None, "not_found", 0, {})
        city_cands = [c for t in search_terms(h["name"]) for c in cache.get(t, [])
                      if judge_card(c, h["name"], h["city"])[1] != "other_city"]
        rows.append({
            "hospital_id": h["hospital_id"], "name": h["name"], "city": h["city"],
            "claimed_accreditation": h["accreditation"], "search_term": used,
            "nabh_name": card.get("nabh_name", ""), "nabh_address": card.get("address", ""),
            "certificate_no": card.get("certificate_no", ""), "nabh_status": card.get("status", ""),
            "certificate_url": card.get("certificate_url", ""), "match_score": score,
            "match": verdict if verdict != "other_city" else "not_found",
            "candidates_in_city": len({c["certificate_no"] for c in city_cands}),
        })
        print(f"{h['hospital_id']} {h['name']}: {rows[-1]['match']} -> {rows[-1]['nabh_name']} {rows[-1]['certificate_no']}")
    browser.close()

    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / "nabh_master_matches.csv"
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"Matches file: {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-master", action="store_true",
                    help="search each hospital in --master by name instead of browsing by city")
    ap.add_argument("--master", default=str(PROCESSED_DATA_DIR / "hospitals_master.csv"))
    ap.add_argument("--max-pages", type=int, default=4, help="result pages to read per name search")
    ap.add_argument("--cities", nargs="+", default=list(CITY_STATE))
    ap.add_argument("--state", help="state name for cities not in CITY_STATE")
    ap.add_argument("--names", nargs="*", help="keep only records mentioning any of these words")
    ap.add_argument("--out", default=str(PROCESSED_DATA_DIR.parent / "interim"))
    ap.add_argument("--delay", type=float, default=2.5, help="seconds to pause between actions")
    ap.add_argument("--max-rounds", type=int, default=30, help="max 'load more' clicks per city")
    ap.add_argument("--headed", action="store_true", help="show the browser window")
    ap.add_argument("--debug", action="store_true", help="also save page.html and a screenshot")
    args = ap.parse_args()

    if not robots_allows():
        sys.exit("robots.txt disallows this page for automated access. Stopping.")

    outdir = pathlib.Path(args.out)
    if args.from_master:
        with sync_playwright() as pw:
            run_master(pw, args, outdir)
        return

    all_rows = []
    with sync_playwright() as pw:
        for city in args.cities:
            try:
                all_rows.extend(run_city(pw, city, args, outdir))
            except Exception as e:
                print(f"{city}: failed -> {e}", file=sys.stderr)

    if all_rows:
        cols = sorted({k for r in all_rows for k in r})
        with open(outdir / "all_cities_nabh.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(all_rows)
        print(f"Combined file: {outdir / 'all_cities_nabh.csv'}")


if __name__ == "__main__":
    main()
