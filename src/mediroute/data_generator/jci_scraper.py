#!/usr/bin/env python3
"""Scrape JCI accredited organizations by city and write an Excel workbook."""

import argparse
import csv
import re
import sys
from pathlib import Path
from urllib.parse import quote

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from playwright.sync_api import sync_playwright

BASE_URL = "https://www.jointcommission.org/en/about-us/recognizing-excellence/find-accredited-international-organizations"


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def city_matches(location_text: str, city: str) -> bool:
    """Match the city as a whole comma-separated part of a location line, not as a substring.

    JCI writes locations inconsistently: 'Chennai, India', 'Aluva, Kochi, Kerala, India',
    'Hosur Road, Anekal taluk, Bangalore, Karnataka, India'. Matching only the first part
    missed the last two (Narayana Health City among them)."""
    wanted = normalize_space(city).casefold()
    for line in location_text.splitlines():
        parts = [normalize_space(p).casefold() for p in line.split(",")]
        if wanted in parts:
            return True
    return False


def page_url(base_url: str, country: str, page: int) -> str:
    url = f"{base_url}?rfkid_7:content_filters=country:eq:{quote(country.strip(), safe='')}"
    if page > 1:
        url += f"&rfkid_7:content_page={page}"
    return url


def scrape(country: str, cities: list[str], headless: bool = True, timeout_ms: int = 60000,
           base_url: str = BASE_URL, cdp_url: str = "") -> list[dict]:
    found: list[dict] = []
    seen: set[tuple[str, str]] = set()

    with sync_playwright() as playwright:
        browser_owned = not bool(cdp_url)
        if cdp_url:
            browser = playwright.chromium.connect_over_cdp(cdp_url)
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()
        else:
            browser = playwright.chromium.launch(headless=headless)
            context = browser.new_context(
                user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"),
                locale="en-US",
            )
            page = context.new_page()
        page.set_default_timeout(timeout_ms)
        page_no = 1

        while page_no <= 100:
            url = page_url(base_url, country, page_no)
            response = page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(1200)
            if response is not None and response.status >= 400:
                raise RuntimeError(
                    f"The JCI website returned HTTP {response.status}. "
                    "The site may be in maintenance or temporarily blocking automated browsers. "
                    "Wait and run the command again later with the same arguments."
                )
            try:
                page.wait_for_selector("main h1", timeout=timeout_ms)
            except Exception as exc:
                body_text = page.locator("body").inner_text(timeout=5000)
                if "maintenance" in body_text.lower() or "we'll be back soon" in body_text.lower():
                    raise RuntimeError("The JCI website is showing its maintenance page. Try again later.") from exc
                raise

            # The result cards render after the page shell; a fixed sleep sometimes read
            # page 1 before its cards existed and silently dropped them. Wait until the
            # number of "IHCO ID" cards is non-zero and stable across two checks.
            last = -1
            for _ in range(30):
                count = page.evaluate("() => (document.querySelector('main')?.innerText.match(/IHCO ID/gi) || []).length")
                if count and count == last:
                    break
                last = count
                page.wait_for_timeout(700)

            names_on_page = page.evaluate("""() => [...document.querySelectorAll('main h1')]
                .map(h => h.innerText.trim())""")
            if page_no > 1 and not names_on_page:
                break

            records = page.evaluate(r"""() => {
                const headings = [...document.querySelectorAll('main h1')].slice(1);
                return headings.map((heading) => {
                    let card = heading.parentElement;
                    let chosenCard = null;
                    let visitWebsite = '';
                    let linkCard = heading.parentElement;
                    for (let level = 0; level < 10 && card; level++) {
                        const allHeadingsInCard = [...card.querySelectorAll('main h1')].filter(h => !/Find JCI Accredited Organizations/.test(h.innerText));
                        const text = card.innerText || '';
                        if (allHeadingsInCard.length === 1 && /IHCO ID\s*:/i.test(text) && text.includes(heading.innerText.trim())) {
                            chosenCard = card;
                            break;
                        }
                        card = card.parentElement;
                    }
                    for (let level = 0; level < 10 && linkCard; level++) {
                        const link = [...linkCard.querySelectorAll('a')].find(a => /Visit website/i.test(a.innerText));
                        if (link) { visitWebsite = link.href; break; }
                        linkCard = linkCard.parentElement;
                    }
                    const cardText = chosenCard ? chosenCard.innerText : heading.parentElement.innerText;
                    const ihcoMatch = cardText.match(/IHCO ID\s*:\s*([0-9]+)/i);
                    return {
                        organization: heading.innerText.trim(),
                        ihco: ihcoMatch ? ihcoMatch[1] : '',
                        locationText: cardText,
                        visitWebsite: visitWebsite
                    };
                });
            }""")

            any_new = False
            for record in records:
                location = record["locationText"]
                for requested_city in cities:
                    city = normalize_space(requested_city)
                    if city_matches(location, city):
                        key = (record["organization"].casefold(), record["ihco"])
                        if key not in seen:
                            seen.add(key)
                            found.append({
                                "Organization": normalize_space(record["organization"]),
                                "City": city,
                                "IHCO ID": record["ihco"],
                                "Visit website": record["visitWebsite"],
                                "Source result page": page_no,
                                "Source URL": url,
                            })
                            any_new = True
                        break

            # The site has a finite number of directly accessible result pages.
            pagination = page.evaluate("""() => [...document.querySelectorAll('a, button')]
                .map(e => e.innerText.trim()).filter(t => /^\\d+$/.test(t)).map(Number)""")
            numeric_pages = sorted(set(pagination))
            if numeric_pages and page_no >= max(numeric_pages):
                break
            page_no += 1

        if browser_owned:
            browser.close()
    return found


def write_excel(records: list[dict], output_file: Path, country: str, cities: list[str]) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Organizations"

    headers = ["Organization", "City", "IHCO ID", "Visit website", "Source result page", "Source URL"]
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)

    for record in records:
        sheet.append([record.get(header, "") for header in headers])

    for row in range(2, sheet.max_row + 1):
        sheet.cell(row, 4).hyperlink = sheet.cell(row, 4).value or None
        sheet.cell(row, 6).hyperlink = sheet.cell(row, 6).value or None
        sheet.cell(row, 4).style = "Hyperlink"
        sheet.cell(row, 6).style = "Hyperlink"

    widths = [55, 18, 14, 38, 18, 95]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions

    summary = workbook.create_sheet("Run Summary")
    summary.append(["Parameter", "Value"])
    summary.append(["Country", country])
    summary.append(["Cities", "; ".join(cities)])
    summary.append(["Organizations found", len(records)])
    summary.append(["Source", BASE_URL])
    summary.column_dimensions["A"].width = 24
    summary.column_dimensions["B"].width = 100

    workbook.save(output_file)


def write_csv(records: list[dict], csv_file: Path) -> None:
    csv_file.parent.mkdir(parents=True, exist_ok=True)
    headers = ["Organization", "City", "IHCO ID", "Visit website", "Source result page", "Source URL"]
    with csv_file.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape JCI organizations for one or more cities.")
    parser.add_argument("--cities", nargs="+", required=True, help="City names, for example: Mumbai Pune Nagpur")
    parser.add_argument("--country", default="India", help="Country filter (default: India)")
    parser.add_argument("--output", default="jci_organizations.xlsx", help="Output Excel filename")
    parser.add_argument("--headed", action="store_true", help="Run a visible browser")
    parser.add_argument("--timeout", type=int, default=60000, help="Page timeout in milliseconds")
    parser.add_argument("--base-url", default=BASE_URL, help=argparse.SUPPRESS)
    parser.add_argument("--cdp-url", default="", help="Existing Chrome DevTools URL, e.g. http://127.0.0.1:9222")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cities = [normalize_space(city) for city in args.cities if normalize_space(city)]
    if not cities:
        print("At least one city is required.", file=sys.stderr)
        return 2

    print(f"Searching {args.country} for: {', '.join(cities)}")
    records = scrape(args.country, cities, headless=not args.headed, timeout_ms=args.timeout,
                     base_url=args.base_url, cdp_url=args.cdp_url)
    output = Path(args.output).resolve()
    write_excel(records, output, args.country, cities)
    csv_output = output.with_suffix(".csv")
    write_csv(records, csv_output)
    print(f"Found {len(records)} unique organizations.")
    print(f"Excel saved to: {output}")
    print(f"CSV saved to: {csv_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
