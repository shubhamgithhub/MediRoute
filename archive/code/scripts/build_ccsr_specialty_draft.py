"""Draft the CCSR category -> speciality table and a CCSR-based Step 1 lookup list (benchmark only).

AHRQ's Clinical Classifications Software Refined (CCSR) groups every ICD-10-CM diagnosis code into
about 540 clinical categories in 22 body systems. Instead of our hand-drawn ICD code ranges
(icd10_block_specialty.csv), a code's speciality comes from its CCSR category:

    ICD-10-CM code  --(AHRQ CCSR file)-->  CCSR category  --(this table, doctor review)-->  speciality

The category table is built from simple, readable rules: a default speciality per body system,
then category rows that belong to another speciality, each with its reason. Every row is
review_status=draft until a doctor reviews it. evidence_type says how strong a match is:

    diagnosis  a condition (kidney stone, heart failure): strong routing evidence
    symptom    a sign or symptom (throat pain, low back pain, fever): weak evidence
    status     an encounter or status (organ transplant status, chemotherapy encounter)

Nothing in the app reads these files yet; scripts/benchmark_step1_ccsr.py compares them with the
current lookup.

Input:  data/raw/ccsr_v2023_1/DXCCSR-Reference-File-v2023-1.xlsx (AHRQ, unchanged copy)
Output: data/medical_taxonomy/ccsr_category_specialty_draft.csv
        data/medical_taxonomy/step1_lookup_ccsr_draft.csv

    PYTHONPATH=src .venv/Scripts/python.exe scripts/build_ccsr_specialty_draft.py
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict

from openpyxl import load_workbook

from mediroute.common.specialties import specialty_names
from mediroute.specialty_routing.step1.lookup import ICD_ORDER_FILE, load_lookup
from mediroute.utils.paths import RAW_DATA_DIR, TAXONOMY_DIR

CCSR_FILE = RAW_DATA_DIR / "ccsr_v2023_1" / "DXCCSR-Reference-File-v2023-1.xlsx"
CATEGORY_TABLE = TAXONOMY_DIR / "ccsr_category_specialty_draft.csv"
LOOKUP_FILE = TAXONOMY_DIR / "step1_lookup_ccsr_draft.csv"

# ----------------------------------------------------------------------------- body-system defaults
SYSTEM_DEFAULT = {
    "BLD": "Hematology & Bone Marrow Transplant", "CIR": "Cardiology", "DEN": "NONE",
    "DIG": "Gastroenterology", "EAR": "ENT", "END": "Endocrinology", "EXT": "NONE",
    "EYE": "Ophthalmology", "FAC": "NONE", "GEN": "Urology", "INF": "General Medicine",
    "INJ": "Orthopaedics", "MAL": "Paediatrics", "MBD": "Psychiatry", "MUS": "Orthopaedics",
    "NEO": "Oncology", "NVS": "Neurology", "PNL": "Paediatrics", "PRG": "Obstetrics & Gynaecology",
    "RSP": "Pulmonology", "SKN": "Dermatology", "SYM": "General Medicine",
}

# ----------------------------------------------------------------------------- category rows
# category: (specialities separated by ";", reason). Categories not listed take the body-system default.
CATEGORY = {
    # circulatory: stroke and brain vessels are neurology; lung vessels are pulmonology
    "CIR012": ("Cardiology", "nonspecific chest pain: symptom"),
    "CIR013": ("Pulmonology;Cardiology", "pulmonary embolism"),
    "CIR014": ("Pulmonology;Cardiology", "pulmonary heart disease"),
    "CIR020": ("Neurology", "cerebral infarction (stroke)"),
    "CIR021": ("Neurosurgery;Neurology", "haemorrhagic stroke"),
    "CIR022": ("Neurology", "sequela of haemorrhagic stroke"),
    "CIR023": ("Neurology", "cerebral artery stenosis"),
    "CIR024": ("Neurology", "other cerebrovascular disease"),
    "CIR025": ("Neurology", "sequela of stroke"),
    "CIR029": ("Cardiothoracic Surgery;Cardiology", "aortic aneurysm: usually surgical"),
    "CIR031": ("General Medicine", "hypotension: nonspecific"),
    "CIR037": ("General Medicine", "vasculitis: no rheumatology speciality in our list"),
    # digestive: teeth are dental, mouth is ENT
    "DIG002": ("NONE", "teeth and gingiva: dental, not routed"),
    "DIG003": ("ENT", "diseases of mouth"),
    # endocrine
    "END007": ("General Medicine", "nutritional deficiency"),
    "END008": ("General Medicine", "malnutrition"),
    "END009": ("Bariatric Surgery;Endocrinology", "obesity"),
    "END011": ("General Medicine", "fluid and electrolyte disorders"),
    "END012": ("Pulmonology", "cystic fibrosis: mainly lung care"),
    "END016": ("General Medicine", "other nutritional and metabolic disorders"),
    "END017": ("General Medicine", "sequela of malnutrition"),
    # encounters / status: only the ones that point to a speciality
    "FAC002": ("Psychiatry", "mental health services"),
    "FAC006": ("Oncology", "encounter for antineoplastic therapy"),
    "FAC007": ("Psychiatry", "mental health conditions"),
    "FAC008": ("Oncology", "neoplasm-related encounter"),
    "FAC013": ("Reproductive Medicine", "procreative management"),
    "FAC023": ("Organ Transplant", "organ transplant status"),
    # genitourinary: kidney medicine is nephrology, female organs are gynaecology
    "GEN001": ("Nephrology", "nephritis / nephrosis"),
    "GEN002": ("Nephrology", "acute renal failure"),
    "GEN003": ("Nephrology", "chronic kidney disease"),
    "GEN004": ("Urology;General Medicine", "urinary tract infection"),
    "GEN005": ("Urology", "urinary tract stones"),
    "GEN006": ("Nephrology;Urology", "other kidney and ureter disease"),
    "GEN009": ("Urology", "haematuria: symptom"),
    "GEN010": ("Nephrology", "proteinuria: finding"),
    "GEN015": ("Reproductive Medicine;Urology", "male infertility"),
    "GEN017": ("Obstetrics & Gynaecology", "nonmalignant breast conditions"),
    "GEN018": ("Obstetrics & Gynaecology", "female pelvic inflammatory disease"),
    "GEN019": ("Obstetrics & Gynaecology", "endometriosis"),
    "GEN020": ("Obstetrics & Gynaecology", "genital prolapse"),
    "GEN021": ("Obstetrics & Gynaecology", "menstrual disorders"),
    "GEN022": ("Obstetrics & Gynaecology", "ovarian cyst"),
    "GEN023": ("Obstetrics & Gynaecology", "menopausal disorders"),
    "GEN024": ("Reproductive Medicine", "female infertility"),
    "GEN025": ("Obstetrics & Gynaecology", "other female genital disorders"),
    # infections
    "INF001": ("Pulmonology", "tuberculosis: mostly pulmonary"),
    "INF002": ("Critical Care;General Medicine", "septicaemia"),
    "INF007": ("Gastroenterology", "viral hepatitis"),
    "INF012": ("Pulmonology;General Medicine", "COVID-19"),
    # injury: fractures, dislocations, sprains stay orthopaedics (default)
    "INJ008": ("Neurosurgery", "traumatic brain injury"), "INJ045": ("Neurosurgery", "traumatic brain injury"),
    "INJ009": ("Neurosurgery", "spinal cord injury"), "INJ046": ("Neurosurgery", "spinal cord injury"),
    "INJ010": ("Emergency Medicine;Critical Care", "internal organ injury"),
    "INJ047": ("Emergency Medicine", "internal organ injury"),
    "INJ011": ("Plastic & Reconstructive Surgery;Emergency Medicine", "open wound head/neck"),
    "INJ048": ("Plastic & Reconstructive Surgery", "open wound head/neck"),
    "INJ012": ("Emergency Medicine", "open wound limbs"), "INJ049": ("Emergency Medicine", "open wound limbs"),
    "INJ013": ("Emergency Medicine", "open wound trunk"), "INJ050": ("Emergency Medicine", "open wound trunk"),
    "INJ015": ("Plastic & Reconstructive Surgery", "amputation of other body parts"),
    "INJ052": ("Plastic & Reconstructive Surgery", "amputation of other body parts"),
    "INJ016": ("Emergency Medicine", "blood vessel injury"), "INJ053": ("Emergency Medicine", "blood vessel injury"),
    "INJ017": ("Emergency Medicine", "superficial injury: weak"), "INJ054": ("Emergency Medicine", "superficial injury"),
    "INJ019": ("Plastic & Reconstructive Surgery;Emergency Medicine", "burns"),
    "INJ056": ("Plastic & Reconstructive Surgery", "burns"),
    "INJ020": ("Emergency Medicine;ENT", "foreign body in an opening"), "INJ057": ("Emergency Medicine", "foreign body"),
    "INJ021": ("Emergency Medicine", "other external causes"), "INJ058": ("Emergency Medicine", "other external causes"),
    "INJ022": ("Emergency Medicine;Critical Care", "drug poisoning"), "INJ059": ("Emergency Medicine", "drug poisoning"),
    "INJ023": ("Emergency Medicine;Critical Care", "toxic effects"), "INJ060": ("Emergency Medicine", "toxic effects"),
    "INJ026": ("Emergency Medicine", "other specified injury"), "INJ063": ("Emergency Medicine", "other injury"),
    "INJ027": ("Emergency Medicine", "unspecified injury"), "INJ064": ("Emergency Medicine", "unspecified injury"),
    "INJ028": ("General Medicine", "adverse drug effect"), "INJ065": ("General Medicine", "adverse drug effect"),
    "INJ029": ("General Medicine", "underdosing"), "INJ066": ("General Medicine", "underdosing"),
    "INJ030": ("General Medicine", "drug induced condition"),
    "INJ031": ("Emergency Medicine", "allergic reaction"), "INJ067": ("Emergency Medicine", "allergic reaction"),
    "INJ032": ("Emergency Medicine", "maltreatment"), "INJ068": ("Emergency Medicine", "maltreatment"),
    "INJ033": ("Cardiology", "cardiovascular device complication"), "INJ069": ("Cardiology", "cardiovascular device"),
    "INJ034": ("Urology", "genitourinary device complication"), "INJ070": ("Urology", "genitourinary device"),
    "INJ036": ("Organ Transplant", "transplanted organ complication"),
    "INJ037": ("General Medicine", "other care complication"), "INJ072": ("General Medicine", "other care complication"),
    "INJ073": ("Emergency Medicine", "injury sequela"), "INJ074": ("Emergency Medicine", "external cause sequela"),
    "INJ075": ("General Medicine", "poisoning sequela"), "INJ076": ("General Medicine", "complication sequela"),
    # congenital
    "MAL001": ("Pediatric Cardiology", "congenital heart disease"),
    "MAL004": ("Neurosurgery;Paediatrics", "nervous system congenital anomalies"),
    "MAL005": ("Plastic & Reconstructive Surgery;ENT", "eye/ear/face/neck malformation"),
    "MAL006": ("Plastic & Reconstructive Surgery", "cleft lip or palate"),
    "MAL008": ("Orthopaedics;Paediatrics", "musculoskeletal congenital"),
    # musculoskeletal: rheumatic diseases have no rheumatology speciality in our list
    "MUS003": ("General Medicine;Orthopaedics", "rheumatoid arthritis"),
    "MUS004": ("Paediatrics;Orthopaedics", "juvenile arthritis"),
    "MUS008": ("General Medicine;Orthopaedics", "immune-mediated arthropathy"),
    "MUS010": ("Orthopaedics", "musculoskeletal pain: symptom"),
    "MUS013": ("Endocrinology;Orthopaedics", "osteoporosis"),
    "MUS024": ("General Medicine", "lupus and connective tissue disorders"),
    "MUS025": ("General Medicine", "other connective tissue disease"),
    "MUS026": ("Neurology", "muscle disorders"),
    "MUS029": ("Plastic & Reconstructive Surgery", "disorders of jaw"),
    "MUS033": ("General Medicine;Orthopaedics", "gout"),
    "MUS036": ("General Medicine", "autoinflammatory syndromes"),
    "MUS038": ("Orthopaedics", "low back pain: symptom"),
    # neoplasms: blood cancers to haematology, brain tumours also neurosurgery
    "NEO048": ("Oncology;Neurosurgery", "brain cancer"),
    "NEO049": ("Oncology;Neurosurgery", "other nervous system cancers"),
    **{f"NEO0{n}": ("Hematology & Bone Marrow Transplant;Oncology", "blood cancer")
       for n in (57, 58, 59, 60, 61, 62, 63, 64, 65, 68)},
    # nervous system
    "NVS014": ("Neurosurgery;Neurology", "CNS abscess"),
    "NVS019": ("Neurology", "nervous system pain: symptom"),
    "NVS021": ("Neurosurgery;Neurology", "postoperative nervous system complication"),
    # respiratory: upper airway is ENT
    "RSP001": ("ENT", "sinusitis"),
    "RSP003": ("General Medicine", "influenza"),
    "RSP004": ("ENT", "tonsillitis"),
    "RSP006": ("ENT", "upper respiratory infection"),
    "RSP007": ("ENT", "other upper respiratory disease"),
    "RSP012": ("Critical Care;Pulmonology", "respiratory failure"),
    # skin
    "SKN003": ("Plastic & Reconstructive Surgery;Dermatology", "pressure ulcer"),
    # symptoms: the body system they point to, weak evidence
    "SYM001": ("Cardiology;Neurology", "syncope"),
    "SYM002": ("General Medicine", "fever"),
    "SYM003": ("Emergency Medicine;Critical Care", "shock"),
    "SYM004": ("Gastroenterology", "nausea and vomiting"),
    "SYM005": ("Gastroenterology;ENT", "dysphagia"),
    "SYM006": ("Gastroenterology", "abdominal symptoms"),
    "SYM007": ("General Medicine", "malaise and fatigue"),
    "SYM008": ("Psychiatry", "mental symptoms"),
    "SYM009": ("Psychiatry", "substance-use findings"),
    "SYM010": ("Neurology", "nervous system symptoms"),
    "SYM011": ("Urology", "genitourinary symptoms"),
    "SYM012": ("Cardiology", "circulatory symptoms"),
    "SYM013": ("Pulmonology;ENT", "respiratory symptoms (cough, breathlessness, throat pain)"),
    "SYM014": ("Dermatology", "skin symptoms"),
    "SYM015": ("Neurology", "sensation/perception symptoms"),
    "SYM016": ("General Medicine", "other general symptoms"),
    "SYM017": ("NONE", "abnormal findings without diagnosis"),
}
SYMPTOM_LIKE = {"CIR012", "CIR031", "GEN009", "GEN010", "MUS010", "MUS038", "NVS019", "INJ017", "INJ054"}


def evidence_type(category: str) -> str:
    if category.startswith("SYM") or category in SYMPTOM_LIKE:
        return "symptom"
    if category.startswith("FAC"):
        return "status"
    return "diagnosis"


def load_ccsr():
    wb = load_workbook(CCSR_FILE, read_only=True, data_only=True)
    categories = {r[0]: r[1] for r in list(wb["CCSR_Categories"].iter_rows(values_only=True))[2:] if r[0]}
    default_category: dict[str, str] = {}
    for row in list(wb["DX_to_CCSR_Mapping"].iter_rows(values_only=True))[2:]:
        code, category, outpatient_default = row[0], row[2], row[5]
        if code and category and (outpatient_default == "Y" or code not in default_category):
            default_category[code] = category  # the outpatient default category wins
    return categories, default_category


def build_category_table(categories: dict[str, str]) -> dict[str, dict]:
    valid = set(specialty_names()) | {"NONE"}
    table = {}
    for cat, desc in categories.items():
        system = cat[:3]
        if cat in CATEGORY:
            specs, basis = CATEGORY[cat][0], "category rule: " + CATEGORY[cat][1]
        elif system in SYSTEM_DEFAULT:
            specs, basis = SYSTEM_DEFAULT[system], "body-system default"
        else:
            specs, basis = "NONE", "not a clinical category"
        unknown = set(specs.split(";")) - valid
        if unknown:
            raise ValueError(f"{cat}: unknown speciality {unknown}")
        table[cat] = {"ccsr_category": cat, "description": desc, "body_system": system, "specialty": specs,
                      "evidence_type": evidence_type(cat), "basis": basis, "review_status": "draft"}
    return table


def build_lookup(table: dict[str, dict], default_category: dict[str, str]) -> tuple[list[dict], Counter]:
    """ICD-10-CM 3/4-character codes (same codes as today's lookup) mapped through CCSR.

    CCSR maps billable codes; a header code ("R07 Pain in throat and chest") takes the category
    of its billable children if they all agree, and is left out if they point to different
    specialities (its children are in the list and carry the detail)."""
    stats = Counter()
    by_prefix: dict[str, Counter] = defaultdict(Counter)
    for code, cat in default_category.items():
        for n in (3, 4):
            by_prefix[code[:n]][cat] += 1
    rows, seen = [], set()
    with ICD_ORDER_FILE.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            code = line[6:13].strip()
            if len(code) not in (3, 4) or code[0] in "VWXY":
                continue
            description = line[77:].strip() or line[16:76].strip()
            children = Counter({default_category[code]: 1}) if code in default_category else by_prefix.get(code, Counter())
            if not children:
                stats["no CCSR category (code newer than CCSR v2023)"] += 1
                continue
            spec_sets = {table[c]["specialty"] for c in children if c in table}
            if len(spec_sets) != 1:
                stats["header with mixed children, left out"] += 1
                continue
            cat = children.most_common(1)[0][0]  # children agree on the speciality; take the commonest category
            entry = table[cat]
            if entry["specialty"] == "NONE":
                stats["category maps to NONE"] += 1
                continue
            for spec in entry["specialty"].split(";"):
                key = (description.lower(), spec)
                if key in seen:
                    continue
                seen.add(key)
                rows.append({"entry_id": f"icd:{code}:{spec}", "source": "icd10cm_ccsr", "code": code,
                             "text": description, "specialty": spec, "ccsr_category": cat,
                             "evidence_type": entry["evidence_type"]})
            stats["mapped"] += 1
    # CGHS procedures and lay terms are unchanged from today's lookup list
    for e in load_lookup():
        if e.source != "icd10cm":
            rows.append({"entry_id": e.entry_id, "source": e.source, "code": e.code, "text": e.text,
                         "specialty": e.specialty, "ccsr_category": "", "evidence_type": "diagnosis"})
    return rows, stats


def main() -> None:
    categories, default_category = load_ccsr()
    table = build_category_table(categories)
    with CATEGORY_TABLE.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(next(iter(table.values()))))
        writer.writeheader()
        writer.writerows(table.values())
    rows, stats = build_lookup(table, default_category)
    with LOOKUP_FILE.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    bases = Counter(r["basis"].split(":")[0] for r in table.values())
    print(f"{len(table)} CCSR categories -> {CATEGORY_TABLE.name}: {dict(bases)}; "
          f"evidence types {dict(Counter(r['evidence_type'] for r in table.values()))}")
    print(f"{len(rows)} lookup entries -> {LOOKUP_FILE.name}; ICD codes: {dict(stats)}; "
          f"by source {dict(Counter(r['source'] for r in rows))}")


if __name__ == "__main__":
    main()
