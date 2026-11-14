"""Label-review file for the 100 gretel messages of the 13 Nov portal test, using one rule for all.

    PYTHONPATH=src python scripts/make_gretel_rule_review.py

Gretel messages list the effects of an illness without naming it, and the dataset's label is the
speciality of that hidden diagnosis. This script applies one labelling rule to every message
instead (draft, to be confirmed by the doctor):

    1 red flag (chest pain with breathlessness / racing heart / dizziness, loss of sight, confusion)
                                          -> Emergency Medicine
    2 the patient names a condition       -> that condition's speciality
    3 symptoms from one body system       -> that system's specialist (General Medicine also accepted)
    4 several body systems, or only general symptoms (fever, chills, tiredness, aches, weight loss)
                                          -> General Medicine

The per-message facts (systems, red flag, named condition) are hand-classified below (draft by
Claude, not a doctor); the label is computed from them by code, the same way for every row.
Writes data/evaluation/step1_gold_gretel_rule_review.csv. Does not change step1_gold_gretel.csv.
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "data" / "evaluation" / "step1_gold_gretel.csv"
RUN = ROOT / "data" / "evaluation" / "portal_runs" / "20261113_223410"
OUT = ROOT / "data" / "evaluation" / "step1_gold_gretel_rule_review.csv"

# body system -> (specialist, extra accepted alternatives besides General Medicine)
SYSTEM = {
    "skin": ("Dermatology", []), "airway": ("Pulmonology", ["ENT"]), "ent": ("ENT", []),
    "eye": ("Ophthalmology", []), "gi": ("Gastroenterology", []), "urinary": ("Urology", []),
    "joints": ("Orthopaedics", []), "nerve": ("Neurology", []), "vascular": ("Cardiothoracic Surgery", ["Cardiology"]),
    "mind": ("Psychiatry", []), "metabolic": ("Endocrinology", []),
}
GENERAL = "fever, chills, sweating, tiredness / weakness, aches, weight loss, loss of appetite, feeling unwell"

# id: (body systems, red flag, named condition "Name=Speciality;alternatives", note)
FACTS = {
    "G083": ("skin", "", "", "Lip and cheek swelling may be an allergy (General Medicine)."),
    "G009": ("joints", "", "", ""),
    "G018": ("airway", "", "", ""),
    "G006": ("joints, airway, nerve", "", "", "Neck pain with limb weakness and imbalance may point to Neurology / Orthopaedics."),
    "G025": ("skin", "", "", "Fever with an itchy rash all over: Paediatrics if a child."),
    "G041": ("airway", "", "cold=General Medicine;ENT", ""),
    "G050": ("gi, nerve", "", "", ""),
    "G019": ("skin, nerve", "", "", "Slow-healing wounds with tingling hands and feet suggest diabetes (Endocrinology)."),
    "G003": ("nerve, mind", "", "migraine=Neurology", ""),
    "G005": ("skin", "", "", ""),
    "G007": ("gi", "", "", ""),
    "G038": ("nerve", "", "", ""),
    "G037": ("skin", "", "", ""),
    "G020": ("gi", "", "", "Yellow skin and urine = jaundice (liver, Gastroenterology)."),
    "G013": ("", "", "", "Only general fever symptoms."),
    "G017": ("nerve, eye", "", "", "Worsening headache with a sore neck and blurred vision may be a red flag: doctor to check."),
    "G001": ("gi", "", "", ""),
    "G004": ("airway, vascular", "can't catch breath + chest pain + racing heart", "", ""),
    "G008": ("skin, joints", "", "", "Rash with joint pain may be psoriasis (Dermatology)."),
    "G014": ("gi", "", "typhoid (suspected)=General Medicine;Gastroenterology", ""),
    "G027": ("urinary", "", "", ""),
    "G063": ("vascular", "", "", ""),
    "G086": ("ent, skin, eye", "", "", ""),
    "G011": ("joints", "", "", ""),
    "G034": ("airway", "", "", ""),
    "G012": ("airway, joints", "disoriented (confusion)", "", ""),
    "G028": ("mind", "", "", "Tiredness, low motivation and poor sleep."),
    "G058": ("airway", "", "", ""),
    "G051": ("", "", "", "Only general symptoms (fever, aches, pain behind the eyes)."),
    "G047": ("airway, skin", "", "", "Recurrent yeast infections may suggest diabetes (Endocrinology)."),
    "G046": ("metabolic", "", "", "Weight gain with appetite changes."),
    "G029": ("skin", "", "", ""),
    "G023": ("gi", "", "", "Chest pain only when leaning or lying down, with heartburn: reflux, not a red flag."),
    "G042": ("nerve, vascular", "chest pain + dizziness", "", ""),
    "G044": ("skin", "", "", ""),
    "G030": ("gi", "", "", "Yellow skin and dark urine = jaundice."),
    "G016": ("", "", "", "Only general fever symptoms."),
    "G021": ("nerve", "", "", ""),
    "G002": ("gi", "", "", ""),
    "G010": ("airway, vascular", "trouble breathing + chest pain", "", ""),
    "G066": ("skin", "", "", ""),
    "G031": ("gi", "", "", "Fever with belly pain."),
    "G049": ("urinary, gi, nerve", "", "", "Blood in urine with pelvic pain may favour Urology."),
    "G100": ("vascular", "", "", ""),
    "G090": ("skin", "", "", "Lip and cheek swelling may be an allergy (General Medicine)."),
    "G026": ("joints", "", "", ""),
    "G062": ("airway", "", "", ""),
    "G032": ("joints, nerve", "", "", "Neck pain with imbalance may point to Neurology / Orthopaedics."),
    "G035": ("skin", "", "", "Paediatrics if a child."),
    "G064": ("airway", "", "", ""),
    "G082": ("joints, gi", "", "", ""),
    "G059": ("metabolic", "", "", "Thirst, frequent urination and weight loss: classic diabetes pattern."),
    "G085": ("skin, nerve", "", "", "Skin peeling off can be a severe drug reaction (emergency): doctor to check."),
    "G040": ("skin", "", "", ""),
    "G036": ("gi", "", "acid reflux=Gastroenterology", ""),
    "G091": ("nerve, vascular", "chest pain + dizziness getting worse", "", ""),
    "G081": ("skin", "", "", ""),
    "G056": ("gi", "", "", "Yellow rash and dark urine = jaundice."),
    "G022": ("skin", "", "", "Itching with fever symptoms; itching counted as skin."),
    "G045": ("eye, nerve", "", "", ""),
    "G015": ("gi", "", "", ""),
    "G033": ("airway, vascular", "can't catch breath + chest pain + racing heart", "", ""),
    "G116": ("skin", "", "", ""),
    "G039": ("gi", "", "", ""),
    "G073": ("urinary", "", "", ""),
    "G138": ("vascular", "", "varicose veins=Cardiothoracic Surgery;Cardiology", ""),
    "G095": ("airway", "", "asthma=Pulmonology", ""),
    "G043": ("joints", "", "", ""),
    "G149": ("airway", "", "", ""),
    "G054": ("joints, nerve", "", "", "Neck pain with imbalance may point to Neurology / Orthopaedics."),
    "G052": ("skin", "", "", ""),
    "G071": ("airway", "", "cold=General Medicine;ENT", ""),
    "G097": ("", "", "", "Only general fever symptoms."),
    "G069": ("urinary, nerve, eye", "lost sight + confused", "", ""),
    "G134": ("ent", "", "", "Aches counted as general symptoms."),
    "G077": ("skin", "", "", ""),
    "G061": ("gi", "", "", ""),
    "G102": ("nerve, vascular", "chest pain + dizziness", "", ""),
    "G088": ("skin", "", "", ""),
    "G074": ("gi", "", "", "Yellow skin = jaundice."),
    "G024": ("skin", "", "", "Itching with fever symptoms; itching counted as skin."),
    "G053": ("nerve", "", "", ""),
    "G068": ("gi", "", "", ""),
    "G048": ("airway, vascular", "shortness of breath + racing heart", "", ""),
    "G123": ("skin, joints", "", "", "Flaky skin with joint pain may be psoriasis (Dermatology)."),
    "G078": ("airway, gi", "", "", ""),
    "G089": ("urinary", "", "", "Headache counted as minor."),
    "G145": ("vascular", "", "varicose veins=Cardiothoracic Surgery;Cardiology", ""),
    "G106": ("ent, skin", "", "", "Sneezing with eye and lip swelling: allergy pattern."),
    "G084": ("joints", "", "", ""),
    "G157": ("airway", "", "", ""),
    "G067": ("joints, nerve, airway", "", "", ""),
    "G076": ("skin", "", "", ""),
    "G072": ("airway", "", "", ""),
    "G112": ("skin, gi, joints", "", "", ""),
    "G070": ("eye, nerve", "", "", ""),
    "G167": ("ent, joints", "", "", "Severe joint pain counted as joints (in G134 the aches were mild)."),
    "G111": ("skin", "", "", ""),
    "G065": ("gi", "", "", ""),
    "G124": ("nerve, vascular", "chest pain + dizziness", "", ""),
}


def rule_label(systems: str, red_flag: str, named: str) -> tuple[str, str, list[str]]:
    if red_flag:
        return "1 red flag", "Emergency Medicine", []
    if named:
        spec = named.split("=", 1)[1].split(";")
        return "2 named condition", spec[0], spec[1:]
    parts = [s.strip() for s in systems.split(",") if s.strip()]
    if len(parts) == 1:
        specialist, extra = SYSTEM[parts[0]]
        return "3 one body system", specialist, extra + ["General Medicine"]
    return ("4 several systems" if parts else "4 general symptoms only"), "General Medicine", []


def main() -> None:
    gold = {r["query_id"]: r for r in csv.DictReader(GOLD.open(encoding="utf-8"))}
    answers = {r["query_id"]: r for r in (json.loads(l) for l in (RUN / "results.jsonl").read_text(encoding="utf-8").splitlines())
               if r["gold_set"] == "gretel"}
    assert set(answers) == set(FACTS), set(answers) ^ set(FACTS)
    rows, tally = [], Counter()
    for qid, (systems, red, named, note) in FACTS.items():
        g, a = gold[qid], answers[qid]
        rule, expected, alts = rule_label(systems, red, named)
        cur = [g["expected_specialty"], *[x for x in g["acceptable_alternatives"].split(";") if x]]
        new = [expected, *alts]
        said = a["specialty"]
        def outcome(ok): return "asks" if said is None else ("correct" if said in ok else "confidently wrong")
        before, after = outcome(cur), outcome(new)
        tally[("before", before)] += 1
        tally[("after", after)] += 1
        tally[("rule", rule[0])] += 1
        tally[("label changed", set(cur) != set(new))] += 1
        rows.append({
            "query_id": qid, "gretel_diagnosis": g["case_type"].replace("gretel:", ""), "patient_message": g["query"],
            "body_systems": systems or "(general symptoms only)", "red_flag": red, "named_condition": named.split("=")[0],
            "rule_applied": rule, "rule_expected": expected, "rule_alternatives": ";".join(alts),
            "current_expected": g["expected_specialty"], "current_alternatives": g["acceptable_alternatives"],
            "label_changes": "yes" if set(cur) != set(new) else "no",
            "mediroute_answer": said or "(asked)", "outcome_current_label": before, "outcome_rule_label": after,
            "note": note,
            "doctor_agrees_with_rule_label": "", "doctor_expected": "", "doctor_alternatives": "", "doctor_note": "",
        })
    with OUT.open("w", encoding="utf-8-sig", newline="") as h:
        w = csv.DictWriter(h, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} rows -> {OUT.relative_to(ROOT)}")
    for k in sorted(tally):
        print(k, tally[k])


if __name__ == "__main__":
    main()
