"""One-off migration (11 Nov 2026): merge every "X -> speciality" rule into one table.

Writes data/processed/specialty_mapping.csv and data/processed/specialties.csv from the old files:

    CCSR category rules     scripts/build_ccsr_specialty_draft.py rules + AHRQ CCSR categories
    CGHS label rules        data/medical_taxonomy/cghs_label_specialty.csv
    CGHS name rules         data/medical_taxonomy/cghs_name_overrides.csv
    lay terms               keywords column of data/medical_taxonomy/specialties.csv
    hospital labels         data/medical_taxonomy/specialty_normalization.csv

After the migration the two processed files are the maintained source; this script and the old
files are kept in archive/ for the record. Lay terms that are body parts, age words or plain
symptoms are marked "weak" (they count half and are not used as evidence on their own).
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
OLD = ROOT / "data" / "medical_taxonomy"
OUT = ROOT / "data" / "processed"

import build_ccsr_specialty_draft as ccsr  # noqa: E402

WEAK_LAY_TERMS = {
    # body parts and organs: say where, not what
    "heart", "cardiac", "bone", "spine", "nerve", "liver", "lung", "ear", "nose", "throat", "voice", "nasal",
    "eye", "eyes", "vision", "skin", "uterus", "ovary", "cervix", "bladder", "urinary", "respiratory",
    # age and family words
    "child", "baby", "infant", "newborn", "toddler", "kid", "my son", "my daughter", "growth",
    # plain symptoms that many specialities see
    "headache", "head pain", "dizziness", "numbness", "tingling", "fainting", "back pain", "back ache",
    "neck pain", "bone pain", "joint pain", "shoulder pain", "knee pain", "stomach pain", "abdominal pain",
    "vomiting", "bloating", "gas", "cough", "breathless", "breathlessness", "shortness of breath", "phlegm",
    "sputum", "breathing problem", "itching", "itchy", "rash", "pelvic pain", "swelling of feet", "puffy face",
    "weight gain", "excessive thirst", "bruising", "lump", "mass", "stress", "fever", "weakness", "tired",
    "fatigue", "body ache", "cold", "infection", "viral", "feeling unwell", "not sure what is wrong",
    # ambiguous words that belong to several specialities
    "bypass", "transplant", "donor", "end stage", "ulcer", "aneurysm", "decompression", "bleeding",
    "emergency", "accident", "trauma", "collapsed", "burns", "reconstruction", "reconstructive", "biopsy",
    "echo", "hormone", "hormonal", "metabolic", "overweight", "bmi", "alcohol", "platelets",
    "blood transfusion", "weight loss without trying", "creatinine",
}

BOUNDARIES = {
    "Cardiology": ("Heart condition managed with medicines, tests or catheter procedures: angina, heart attack care, arrhythmia, heart failure, high blood pressure, angioplasty, stents, pacemaker",
                   "A planned heart or chest operation (bypass, valve replacement) → Cardiothoracic Surgery; a child's heart defect → Pediatric Cardiology; breathlessness from lung disease → Pulmonology"),
    "Cardiothoracic Surgery": ("A heart, lung, chest or aortic operation is planned or recommended: bypass (CABG), valve repair or replacement, open-heart surgery, aortic aneurysm surgery",
                               "Medicines, angiography or stents only → Cardiology; heart surgery for a child's congenital defect → Pediatric Cardiology"),
    "Pediatric Cardiology": ("A baby or child with a heart problem, usually present from birth: hole in the heart (VSD/ASD), tetralogy of Fallot, blue baby",
                             "Heart disease in an adult → Cardiology"),
    "Oncology": ("Confirmed or suspected cancer and its treatment: chemotherapy, radiotherapy, cancer surgery",
                 "Blood cancers (leukaemia, lymphoma, myeloma) and bone marrow transplant → Hematology & Bone Marrow Transplant; brain tumour surgery → Neurosurgery"),
    "Hematology & Bone Marrow Transplant": ("Blood disorders and blood cancers: anaemia, thalassaemia, sickle cell, haemophilia, leukaemia, lymphoma, myeloma; bone marrow or stem cell transplant",
                                            "Kidney, liver, heart or lung transplant → Organ Transplant; solid tumours → Oncology"),
    "Orthopaedics": ("Bones, joints, ligaments and spine: fractures, arthritis, joint replacement, sports injuries, slipped disc, back and neck problems",
                     "Brain or spinal cord surgery for tumours or nerve compression → Neurosurgery; nerve disease without an injury → Neurology"),
    "Neurology": ("Brain and nerve conditions treated without surgery: stroke, epilepsy, migraine, Parkinson's disease, dementia, neuropathy, multiple sclerosis",
                  "Brain tumour, aneurysm or spine surgery → Neurosurgery; a problem of the eye itself → Ophthalmology"),
    "Neurosurgery": ("Surgery on the brain, spinal cord or nerves: brain tumour, aneurysm, hydrocephalus, spinal cord compression, head injury surgery",
                     "Stroke, epilepsy or headaches treated without surgery → Neurology"),
    "Gastroenterology": ("Stomach, intestines, liver, pancreas and gallbladder: acidity, ulcers, liver disease, jaundice, inflammatory bowel disease, endoscopy, colonoscopy",
                         "Liver transplant → Organ Transplant; cancer of a digestive organ → Oncology"),
    "Nephrology": ("Kidney disease treated with medicines or dialysis: chronic kidney disease, kidney failure, protein in urine",
                   "Kidney or ureter stones, prostate and bladder problems → Urology; kidney transplant → Organ Transplant"),
    "Urology": ("Urinary tract and male reproductive organs: kidney and ureter stones, prostate, bladder, urine infection, incontinence",
                "Kidney failure or dialysis → Nephrology; male infertility treatment → Reproductive Medicine"),
    "Organ Transplant": ("Solid-organ transplant: kidney, liver, heart or lung, including living donor transplants",
                         "Bone marrow or stem cell transplant → Hematology & Bone Marrow Transplant; hair transplant → Plastic & Reconstructive Surgery"),
    "Obstetrics & Gynaecology": ("Pregnancy, childbirth and women's reproductive organs: periods, fibroids, ovarian cysts, menopause, hysterectomy",
                                 "Infertility or IVF → Reproductive Medicine; cancer of the breast, uterus or ovary → Oncology"),
    "Reproductive Medicine": ("Trouble conceiving and fertility treatment: IVF, IUI, ICSI, egg freezing, male or female infertility",
                              "Pregnancy care and delivery → Obstetrics & Gynaecology"),
    "Paediatrics": ("Children's general health and childhood illnesses, newborn and premature baby care",
                    "A child whose problem has its own speciality is routed by the problem: heart defect → Pediatric Cardiology, cleft lip → Plastic & Reconstructive Surgery, liver transplant → Organ Transplant"),
    "Endocrinology": ("Hormone and gland conditions: diabetes, thyroid, PCOS, pituitary and adrenal disorders",
                      "Weight-loss surgery → Bariatric Surgery; diabetic damage to the eyes or kidneys → Ophthalmology or Nephrology"),
    "Pulmonology": ("Lungs and breathing: asthma, COPD, tuberculosis, pneumonia, persistent cough, sleep apnoea",
                    "Chest pain with heart symptoms → Cardiology; a patient on a ventilator or in intensive care → Critical Care"),
    "Plastic & Reconstructive Surgery": ("Reconstruction and repair: burn scars, cleft lip and palate, skin grafts, cosmetic surgery, hair transplant",
                                         "A fresh burn injury → Emergency Medicine"),
    "Bariatric Surgery": ("Severe obesity where weight-loss surgery is considered: gastric sleeve, gastric bypass, gastric balloon",
                          "Hormonal causes of weight gain → Endocrinology"),
    "Emergency Medicine": ("Accidents, injuries, poisoning, severe allergic reactions and other problems needing care now",
                           "A planned or long-standing problem → the speciality that treats it"),
    "Critical Care": ("A critically ill patient who needs intensive care: ICU, ventilator, sepsis, multi-organ failure",
                      "Urgent but stable problems → Emergency Medicine"),
    "Ophthalmology": ("Eyes and vision: cataract, glaucoma, retina, squint, eye infections, LASIK",
                      "Vision loss caused by a brain or nerve condition → Neurology"),
    "ENT": ("Ear, nose, throat and voice: hearing loss, sinusitis, tonsils, hoarse voice, cochlear implant",
            "Lung or breathing disease → Pulmonology; cancer of the mouth or throat → Oncology"),
    "Dermatology": ("Skin, hair and nails: rashes, eczema, psoriasis, acne, fungal infections, hair loss",
                    "Burn scars or skin reconstruction → Plastic & Reconstructive Surgery"),
    "Psychiatry": ("Mental health: depression, anxiety, panic, bipolar disorder, schizophrenia, addiction, sleep problems",
                   "Memory loss from dementia → Neurology"),
    "General Medicine": ("General or unclear illness and infections: fever, malaria, dengue, typhoid, fatigue, health check-ups",
                         "A message that names a specific condition or procedure → that speciality"),
}

FIELDS = ["source", "value", "description", "specialty", "evidence_type", "reason", "review_status"]


def read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    rows: list[dict] = []
    # CCSR categories (AHRQ grouping of ICD-10-CM; our category -> speciality rules)
    categories, _ = ccsr.load_ccsr()
    for cat, r in ccsr.build_category_table(categories).items():
        rows.append({"source": "ccsr", "value": cat, "description": r["description"], "specialty": r["specialty"],
                     "evidence_type": r["evidence_type"] if r["specialty"] != "NONE" else "",
                     "reason": r["basis"].replace("category rule: ", ""), "review_status": "draft"})
    # CGHS: name rules first (they win over the label), then section labels
    for r in read(OLD / "cghs_name_overrides.csv"):
        rows.append({"source": "cghs_name", "value": r["name_contains"].strip(), "description": "",
                     "specialty": r["specialty"].strip(), "evidence_type": "procedure",
                     "reason": r.get("notes", "").strip() or "procedure name rule", "review_status": r["review_status"]})
    for r in read(OLD / "cghs_label_specialty.csv"):
        spec = r["specialty"].strip()
        rows.append({"source": "cghs_label", "value": r["cghs_label"].strip(), "description": "",
                     "specialty": spec, "evidence_type": "procedure" if spec != "NONE" else "",
                     "reason": r.get("notes", "").strip() or "CGHS section label", "review_status": r["review_status"]})
    # lay terms: one row per term (a term listed under two specialities keeps both)
    lay: dict[str, list[str]] = defaultdict(list)
    specs = read(OLD / "specialties.csv")
    for s in specs:
        for kw in s["keywords"].split(";"):
            kw = kw.strip().lower()
            if kw and s["specialty"] not in lay[kw]:
                lay[kw].append(s["specialty"])
    for term, names in lay.items():
        weak = term in WEAK_LAY_TERMS
        rows.append({"source": "lay_term", "value": term, "description": "", "specialty": ";".join(names),
                     "evidence_type": "weak" if weak else "strong",
                     "reason": "body part, age word, plain symptom or ambiguous word" if weak else "patient wording",
                     "review_status": "draft"})
    # hospital department names (Step 2): one row per label, several specialities joined
    status_map = {"reviewed": "reviewed", "draft_rule": "draft", "review_needed": "review_needed"}
    labels: dict[str, dict] = {}
    for r in read(OLD / "specialty_normalization.csv"):
        raw, canon = r["raw_specialty"].strip(), r["canonical_specialty"].strip()
        entry = labels.setdefault(raw, {"names": [], "notes": r.get("notes", "").strip(),
                                        "status": status_map.get(r["normalization_status"], "draft")})
        if canon and canon not in entry["names"]:
            entry["names"].append(canon)
    for raw, e in labels.items():
        names = [n for n in e["names"] if n != "NONE"] or ["NONE"]
        rows.append({"source": "hospital", "value": raw, "description": "", "specialty": ";".join(names),
                     "evidence_type": "", "reason": e["notes"] or "hospital department name",
                     "review_status": e["status"]})

    # values are matched case-insensitively, so "ENT Investigation" / "ENT investigation" are one rule
    seen, unique = set(), []
    for r in rows:
        key = (r["source"], r["value"].casefold())
        if key not in seen:
            seen.add(key)
            unique.append(r)
    rows = unique

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "specialty_mapping.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    with (OUT / "specialties.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["specialty", "care_category", "description",
                                                    "route_here_when", "not_here"])
        writer.writeheader()
        for s in specs:
            when, not_here = BOUNDARIES[s["specialty"]]
            writer.writerow({"specialty": s["specialty"], "care_category": s["care_category"],
                             "description": s["description"], "route_here_when": when, "not_here": not_here})

    counts = defaultdict(int)
    for r in rows:
        counts[r["source"]] += 1
    weak = sum(r["source"] == "lay_term" and r["evidence_type"] == "weak" for r in rows)
    print(f"specialty_mapping.csv: {len(rows)} rules {dict(counts)}; lay terms weak {weak}")
    print(f"specialties.csv: {len(specs)} specialities with route_here_when / not_here")


if __name__ == "__main__":
    main()
