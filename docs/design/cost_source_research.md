# Treatment cost sources: research findings

**Date:** 2026-11-06 · **Author:** Pravin (with Claude Code) · **For:**
[treatment_cost_data_design.md](treatment_cost_data_design.md), step "find real prices first, CGHS
fallback second"

**Question:** where can we get the treatment price at **a named hospital** in our 14 cities, from
official or public sources, before falling back to scaled CGHS rates?

**Short answer:**

- **No hospital publishes its own package prices** in a usable form. Searches across our flagship
  hospitals found enquiry forms, consultation fees and city-level marketing ranges, but no
  per-procedure price list.
- **Two aggregator sites have per-hospital prices and allow automated access**:
  - **MediGence**: "starting from" USD prices per hospital, aimed at international patients.
  - **Bajaj Finserv Health**: min/average/max INR per hospital, but only for a few surgeries.
- **Official government data is strong for the CGHS fallback.** The revised CGHS rules
  (13 Oct 2025) confirm every multiplier in our model, including the ward factors that were still
  unverified.

**Recommendation:** build the CGHS estimate as the base for every hospital. Add MediGence (and
optionally Bajaj Finserv Health) as a per-hospital "reported price" for the hospitals they cover,
once the team agrees on decision 5 below.

---

## 1. What we looked for

The sources you suggested: hospital websites, Google reviews, aggregator/vendor sites, Practo-like
platforms and surgical-package sites. We added government schedules. For each source we checked:

1. Does it give a price for a **named hospital** (or only a city/India range)?
2. Is the page structured (a table or cards) and readable without login?
3. Does `robots.txt` allow automated access, and is anything said about reuse?
4. How many of **our** hospitals does it cover?

## 2. Findings by source

### 2.1 Hospital websites (official)

| Hospital / group | What was found | Usable? |
|------------------|----------------|---------|
| Apollo (apollo247.com cost articles) | Factors and advice only; no price for bypass. Consultation fees per doctor | No |
| CARE Hospitals (`carehospitals.com/surgery-cost/...`) | Search snippets show city ranges (e.g. knee replacement ₹1.5–6 L in India, ₹1.5–3.5 L in Aurangabad). The site refused automated connections | City ranges only; not fetchable |
| Manipal Old Airport Road | An inpatient **tariff PDF** (effective 01-04-2023) exists, but `robots.txt` disallows `/uploads/pdf/` and all `.pdf` | No (disallowed) |
| Medanta, Kokilaben, Narayana, Amrita | No published package prices found. Prices appear only on aggregators | No |
| AIIMS New Delhi | Publishes "revised rates of hospital charges" and operative-procedure rates, but the indexed URLs now return 404. A 2011 decision says AIIMS private-ward procedure charges are at par with CGHS rates | Needs the current URL; worth one manual check |

**Conclusion:** hospital-published prices are not a viable automated source for our hospitals.
Keep rank 1 (`published_hospital`) in the schema for manual entry when a hospital sends a quote or
publishes a package.

### 2.2 Aggregator and vendor sites

| Site | Per-hospital prices? | Format | `robots.txt` (user-agent `*`) | Our hospitals covered (sample) | Verdict |
|------|----------------------|--------|-------------------------------|-------------------------------|---------|
| **[MediGence](https://medigence.com/clinics/cardiac-sciences/cabg/india)** | **Yes**: "Starting USD x" on each hospital card, 73 hospitals for CABG | Plain HTML, paginated (`?page=2..5`) | `/clinics/` allowed. Disallows only estimate/cost-trend loaders, booking and enquiry forms | CABG: BLK-Max $6,500, Artemis $6,500, Medanta $5,500, Gleneagles Mumbai $7,000, Fortis Escorts $5,500, Fortis Malar $4,500, Global Health City $4,200; some show no price | **Best candidate.** "Starting from" prices, no date or inclusions |
| **[Bajaj Finserv Health](https://www.bajajfinservhealth.in/hospitals/chennai/apollo-hospital-greams-rd-thousand-lights/surgeries)** | **Yes**, on each hospital's `/surgeries` page: min / average / max INR | Plain HTML | `/hospitals/` and `/surgeries/` allowed (query strings like `?selectedSurgery=` disallowed). Content-Signal: `search=yes, ai-train=no, use=reference` | Apollo Greams Road: CABG ₹1–8 L (avg ₹7 L), angiogram ₹21–50 k, mitral valve ₹10–30 L. Only 3 of 27 listed surgeries had prices | Usable but thin; min/max look inconsistent (CABG text inverts them) |
| [Credihealth](https://credihealth.com/procedures/chennai/knee-replacement-cost) | Yes, "hospital-wise" tables (search snippet: Chennai knee replacement MIOT ₹2–4.5 L, Fortis Malar ₹2.2–4.8 L, Apollo Greams ₹2.5–5 L, SIMS ₹2.1–4.7 L) | Unknown | **Site returns 403 to automated clients** (robots.txt too) | Good, from snippets | **Not collectable.** Cite manually as a cross-check only |
| [Bookimed](https://health.bookimed.com/clinic/m/medanta---the-medicity) | Yes, per clinic (e.g. Medanta angioplasty from $6,500, liver transplant from $42,000) | — | **`Disallow: /` for all agents** | Some | **Off limits** |
| [LyfBoat](https://www.lyfboat.com/hospitals/coronary-bypass-surgery-cabg-hospitals-and-costs-in-india/) | Per-hospital cost pages | — | Allows `*` but blocks AI crawlers; returned 403 | — | Not collectable |
| [Policybazaar](https://www.policybazaar.com/health-wellness/surgery/bypass-surgery-cost/chennai) | City ranges (Chennai bypass min ₹3.5–8.4 L, max ₹6.3–12.5 L) | — | Timed out | No per-hospital | City cross-check only |
| [Pristyn Care](https://www.pristyncare.com/cost/cataract/) | Its own clinic network's prices (cataract ₹30–40 k) | — | Not checked | Not our hospitals | Not relevant |
| [Practo](https://www.practo.com/chennai/hospitals/knee-replacement) | **No prices**; hospital listings and consultation fees | — | Hospital paths allowed | — | No |
| HexaHealth | Price pages not found at expected URLs | — | Allows `*` | — | Needs a manual look; not pursued |
| Lybrate, myUpchar, LoginToHealth | City/India ranges | — | — | No per-hospital | No |

**Caution with aggregator prices:**

- They are **marketing estimates**. None of the pages we read gives a date, inclusions, or how the
  numbers were derived.
- Prices are "starting from" values, not typical ones.
- Sources disagree widely. Chennai CABG ranges from ₹1.2–4.5 L (Bajaj) to ₹3.5–12.5 L
  (Policybazaar).

So aggregator figures should be stored as `cost_basis = aggregator`, `confidence = Low`, with the
URL and retrieval date, and labelled "reported by <site>" in the app.

### 2.3 Google reviews

Not usable:

- The Places API returns at most **5 reviews per place**.
- The Google Maps Platform terms have a "No Scraping" clause covering reviews.
- Prices mentioned in reviews are unstructured and rare.

At most a teammate could note anecdotal prices by hand. We don't recommend it.

### 2.4 Government and regulated sources

| Source | What it gives | Use in our design |
|--------|---------------|-------------------|
| **CGHS revised rates (13 Oct 2025)** | ~2,000 procedures × Tier I/II/III × NABH / non-NABH / super speciality, semi-private ward. Our `CGHS_Data` sheet matches this structure exactly | **Base of every estimate** |
| CGHS rules ([gconnect summary](https://www.gconnect.in/cghs-apps/treatment-rates/guidelines/overview)) | Tier II −10%, Tier III −20%; non-NABH −15%; super speciality +15%; general ward −5%, private ward +5% (packages only; investigations, consultations and radiotherapy are the same in every ward); implants (stents, valves, lenses) paid **in addition** at CGHS/NPPA ceilings; medicines and consumables inclusive | Confirms every multiplier in the model, including `f_ward` |
| CGHS super-speciality definition ([gconnect](https://www.gconnect.in/cghs-apps/treatment-rates/guidelines/super-specialty)) | **≥ 200 beds**, NABH (or JCI) accredited, and CGHS-empanelled facilities in nephro-urology/renal transplant, neurosurgery, cardiothoracic surgery, oncology (medical, surgical, radiation), transplant, endocrinology, joint replacement, GI surgery/transplant. Uplift applies only to super-speciality procedures | Replaces our guessed rule (decision 3) |
| City classes ([ECHS addendum to the CGHS OM](https://www.echs.gov.in/assets/policy/ADDENDUM%20TO%20IMPLEMENTATION%20OF%20NEWLY%20REVISED%20CGHS%20RATES%20FOR%20ECHS.pdf)) | Rates follow the HRA X/Y/Z city classes. **Gurugram, Faridabad, Ghaziabad and Noida take Delhi rates. Panchkula and Mohali take Chandigarh rates** | Decision 2 (see §3) |
| [NPPA ceiling prices](https://medicaldialogues.in/news/industry/medical-devices/nppa-revises-coronary-stent-prices-des-at-rs-39186-and-bms-at-rs-10762-from-april-2026-168192) | Drug-eluting stent ₹39,186, bare-metal stent ₹10,762 (from 1 Apr 2026, excl. GST). Knee-implant caps extended to 15 Nov 2026 | Implant add-on for angioplasty and knee replacement |
| [PM-JAY HBP 2022](https://nha.gov.in/img/resources/HBP-2.2-manual.pdf) | 1,949 bundled packages with city-tier pricing; the government insurance scheme's rates | Sanity lower bound only |
| AIIMS / PGIMER user charges | Official prices for those two government hospitals; current URLs not found | Manual check for H039 / H045 |

## 3. Corrections to the design

1. **City → CGHS tier (decision 2).** Gurugram is **Tier I** (Delhi rates, official addendum).
   Proposed map:

   | Tier | Cities | Basis |
   |------|--------|-------|
   | Tier I (X) | New Delhi, Gurugram, Mumbai, Navi Mumbai, Chennai, Kolkata, Bengaluru, Hyderabad, Ahmedabad, Pune | HRA X list; Gurugram per the CGHS/ECHS addendum. **Pune: an unofficial CGHS site lists it as Y, which conflicts with the HRA list. To confirm** |
   | Tier II (Y) | Chandigarh (incl. Mohali, Panchkula), Nagpur, Kochi, Visakhapatnam | HRA Y list; Mohali/Panchkula per the addendum. Kochi and Visakhapatnam not confirmed in a CGHS source |

2. **Super-speciality rule (decision 3).** Use the CGHS definition: NABH or JCI accredited **and**
   ≥ 200 beds **and** offering the listed super-specialities. The master has no bed count, so the
   proposal is: a hospital qualifies if it is accredited (NABH or JCI) and `hospital_type` contains
   "quaternary". Add a `bed_count` column later if the team wants the exact rule.
3. **`f_ward`** is now confirmed, not assumed: 0.95 / 1.00 / 1.05, packages only.
4. **Implants** are always extra in CGHS, so add the NPPA ceiling for stents and knee implants,
   and flag other implants in `notes`.
5. **Aggregator prices (decision 5).** The design said "calibration only, never shown". Given what
   exists, the options are:
   - (a) Keep calibration only.
   - (b) Show MediGence / Bajaj prices as a separate "reported by <site>" line next to the CGHS
     estimate, with Low confidence.
   - (c) Don't use them.

   **Recommendation: (b) for MediGence only**, after a teammate reads its terms of use. It is the
   only source with per-hospital prices for international patients (USD), allows automated access,
   and covers many of our flagship hospitals.

## 4. Coverage expectation

| Source | Expected coverage of our 100 hospitals × 17 basket treatments |
|--------|---------------------------------------------------------------|
| CGHS estimate | 100% of treatments with a CGHS code (16 of 17; IVF has none) |
| MediGence | Roughly 30–50 of our hospitals (private flagships) for 5–10 high-volume procedures; to be measured |
| Bajaj Finserv Health | Few prices per hospital (3 of 27 surgeries at Apollo Greams Road) |
| Hospital-published | ~0 automated; manual entries only |
| Government user charges | AIIMS / PGIMER if the current lists are found |

## 5. MediGence as a comparator, related GitHub work, academic references

### 5.1 MediGence does what MediRoute does, commercially

From [medigence.com](https://medigence.com/) and its [about page](https://medigence.com/about-us):

- **What it is:** a medical-tourism platform, "Free for patients", that earns from hospitals
  ("Hospitals pay us only after you arrive safely"). It covers 20+ destinations including India.
- **Intake:** a "Describe your Medical Condition" form plus report upload. A "doctor-trained
  coordinator" replies.
- **Matching:** hospitals are ranked by an AI engine ("Salus") by "best-fit success rate for
  patients like you". The method, outcome data and validation are not published.
- **Extras:** fixed USD package prices, visa, travel and recovery services.

It is the closest commercial comparator to MediRoute and fits the README's "opaque AI matching"
baseline. Its prices are partner-hospital marketing prices, which is a further reason to label them
"reported by MediGence" (decision 5).

### 5.2 GitHub search (2026-11-06)

Searched GitHub repositories for MediGence, medical tourism in India, hospital recommendation, CGHS
rates, PM-JAY packages and treatment cost in India.

| Repo | What it is | Useful for us? |
|------|-----------|----------------|
| Repos named "medigence" (e.g. [abhipatil1403/MedBridge-MediGence](https://github.com/abhipatil1403/MedBridge-MediGence), [Rishabh4179/MedigenceAI](https://github.com/Rishabh4179/MedigenceAI)) | Interview assignments and unrelated apps; none uses MediGence data | No |
| [naseeya/MediRoute-INDIA](https://github.com/naseeya/MediRoute-INDIA), [niteshpr85/AI-HealthCare](https://github.com/niteshpr85/AI-HealthCare) | **Other projects also called "MediRoute"**: AI healthcare navigator and cost estimator for India (symptoms → ICD-10 → hospitals → cost). The second says it uses "JSON-based mock datasets" | Name clash to be aware of; no reusable verified data |
| [SUKUMAR-PUBLICHEALTH/PMJAY_Price_Variation_Analysis](https://github.com/SUKUMAR-PUBLICHEALTH/PMJAY_Price_Variation_Analysis) | Claims private cardiac prices are **2–4× PM-JAY rates**, from "market-reported" prices | Supports the market-factor range, but the data folder is empty, so it can't be verified |
| [yahiyabinhadi7-del/CGHS-RATES](https://github.com/yahiyabinhadi7-del/CGHS-RATES) | Encoded JSON of CGHS rates (2025 structure, incl. implant and ward-charge categories) | Optional cross-check of our sheet |
| [krishgarg97/insurancesetu](https://github.com/krishgarg97/insurancesetu) | Insurance-claim checker that audits bills against government rate cards; its `RESEARCH.md` lists literature on Indian healthcare costs | Reading list (below) |

### 5.3 Academic references for the market factor (`f_market`)

| Reference | Finding | Use |
|-----------|---------|-----|
| Babu et al., *Hospital Topics* 2024, [doi:10.1080/00185868.2024.2359553](https://informahealthcare.com/doi/full/10.1080/00185868.2024.2359553) | Government package amounts cover only 26–52% of costs at private medical-college hospitals; they need 25–50% more than current rates | Cost floor: private cost ≥ 1.3–2× package rate |
| Karnataka costing vs CGHS vs PM-JAY ([Deccan Herald, 2018](https://www.deccanherald.com/india/private-hospitals-oppose-ayushman-bharat-package-674807.html)) | Bypass: ₹1.88 L state cost vs ₹1.13 L CGHS vs ₹1.10 L PM-JAY (~1.7×). Knee replacement: ₹1.98 L vs ₹1.49 L CGHS (~1.3×) vs ₹0.80 L PM-JAY (~2.5×) | Cost (not price) ratio to CGHS: 1.3–1.7× |
| Health-benefit package costing study, [Springer AHEHP 2020](https://link.springer.com/doi/10.1007/s40258-020-00631-3) | 61% of PM-JAY HBP prices were raised and 18% lowered after cost evidence; PM-JAY rates set ~15–20% below CGHS | Relation between PM-JAY and CGHS |
| [Manipal study on UHC and private hospitals](https://impressions.manipal.edu/open-access-archive/10968/) | Private-hospital view of government package adequacy | Background |

**Implication:** published evidence puts private **cost** at about 1.3–2× CGHS. Private
**prices** to self-paying international patients sit above cost. The design's starting
`f_market` (private Tier 1 = 2.5, Tier 2 = 1.8, trust = 1.4) sits at the upper end of this evidence.
Keep these values as the starting point, cite the studies above, and calibrate against MediGence
prices if decision 5 allows.

## 6. Constraints we followed

- `robots.txt` was checked before reading any site, and blocked sites were not retried. A
  browser-based retry of sites that refused automated clients was stopped by the session's safety
  check, so those sites (Credihealth, CARE, LyfBoat) are treated as **not collectable**.
- No login-only, form-gated or `robots.txt`-disallowed pages are used.
- Any collector must identify itself, wait between requests, and store the source URL and date.

## Sources

- CGHS 2025 revision: [Business Today](https://www.businesstoday.in/amp/personal-finance/retirement-planning/story/biggest-cghs-overhaul-in-15-years-what-changes-for-govt-employees-and-pensioners-now-496882-2025-10-06), [Free Press Journal](https://www.freepressjournal.in/amp/business/new-cghs-rates-to-take-effect-from-tomorrow-treatment-in-super-specialty-hospitals-to-become-costlier), [gconnect: overview](https://www.gconnect.in/cghs-apps/treatment-rates/guidelines/overview), [package rates](https://www.gconnect.in/cghs-apps/treatment-rates/guidelines/package-rates), [super speciality](https://www.gconnect.in/cghs-apps/treatment-rates/guidelines/super-specialty), [ECHS addendum](https://www.echs.gov.in/assets/policy/ADDENDUM%20TO%20IMPLEMENTATION%20OF%20NEWLY%20REVISED%20CGHS%20RATES%20FOR%20ECHS.pdf)
- NPPA: [stent ceiling 2026](https://medicaldialogues.in/news/industry/medical-devices/nppa-revises-coronary-stent-prices-des-at-rs-39186-and-bms-at-rs-10762-from-april-2026-168192), [knee implant cap to Nov 2026](https://medicaldialogues.in/amp/news/industry/medical-devices/nppa-continues-price-cap-on-orthopedic-knee-replacement-implants-for-another-year-till-november-15-2026-158881)
- PM-JAY: [HBP 2.2 manual](https://nha.gov.in/img/resources/HBP-2.2-manual.pdf), [HBP 2022 launch](https://pib.gov.in/PressReleasePage.aspx?PRID=1812209)
- Aggregators: [MediGence CABG India](https://medigence.com/clinics/cardiac-sciences/cabg/india), [Bajaj Finserv Health Apollo Greams Road](https://www.bajajfinservhealth.in/hospitals/chennai/apollo-hospital-greams-rd-thousand-lights/surgeries), [Credihealth Chennai knee](https://credihealth.com/procedures/chennai/knee-replacement-cost), [Bookimed Medanta](https://health.bookimed.com/clinic/m/medanta---the-medicity), [Policybazaar Chennai bypass](https://www.policybazaar.com/health-wellness/surgery/bypass-surgery-cost/chennai), [Pristyn Care cataract](https://www.pristyncare.com/cost/cataract/), [Practo Chennai](https://www.practo.com/chennai/hospitals/knee-replacement)
- Hospital sites: [CARE knee cost](https://carehospitals.com/surgery-cost/knee-replacement-cost), [Apollo247 bypass](https://www.apollo247.com/health-topics/heart-attack/open-heart-bypass-surgery-cost), [Manipal tariff PDF](https://www.manipalhospitals.com/oldairportroad/uploads/pdf/schedule-of-inpatient-tariff-with-effective-from-oldairportroad.pdf)
- Google reviews: [Places API 5-review limit and scraping terms](https://processwire.com/talk/topic/27953-strategies-for-including-google-places-reviews)
