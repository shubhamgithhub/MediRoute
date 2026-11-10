"""Build an independent Step 1 test set from gretelai/symptom_to_diagnosis (Apache-2.0).

The dataset labels patient-style symptom text with one of 22 diagnoses. We map each diagnosis to
the specialty a patient should see first, plus acceptable alternatives. The mapping below is the
team's judgement and should be reviewed (ideally by a doctor).

Usage:
    python scripts/prepare_gretel_gold.py            # downloads test.jsonl, writes the CSV
"""

from __future__ import annotations

import csv
import json
import urllib.request

from mediroute.common.specialties import specialty_names
from mediroute.utils.paths import DATA_DIR

URL = "https://huggingface.co/datasets/gretelai/symptom_to_diagnosis/resolve/main/test.jsonl"
OUT = DATA_DIR / "evaluation" / "step1_gold_gretel.csv"

# diagnosis -> (expected specialty, acceptable alternatives)
DIAGNOSIS_TO_SPECIALTY = {
    "drug reaction": ("General Medicine", ["Dermatology", "Emergency Medicine"]),
    "allergy": ("General Medicine", ["ENT", "Dermatology"]),
    "chicken pox": ("General Medicine", ["Dermatology", "Paediatrics"]),
    "diabetes": ("Endocrinology", ["General Medicine"]),
    "psoriasis": ("Dermatology", []),
    "hypertension": ("Cardiology", ["General Medicine"]),
    "cervical spondylosis": ("Orthopaedics", ["Neurology", "Neurosurgery"]),
    "bronchial asthma": ("Pulmonology", []),
    # vascular surgery sits under cardiothoracic and vascular surgery (CTVS) in Indian hospitals
    "varicose veins": ("Cardiothoracic Surgery", ["General Medicine", "Dermatology"]),
    "malaria": ("General Medicine", []),
    "dengue": ("General Medicine", []),
    "arthritis": ("Orthopaedics", ["General Medicine"]),
    "impetigo": ("Dermatology", ["Paediatrics", "General Medicine"]),
    "fungal infection": ("Dermatology", []),
    "common cold": ("General Medicine", ["ENT"]),
    "gastroesophageal reflux disease": ("Gastroenterology", ["General Medicine"]),
    "urinary tract infection": ("Urology", ["General Medicine", "Nephrology"]),
    "typhoid": ("General Medicine", ["Gastroenterology"]),
    "pneumonia": ("Pulmonology", ["General Medicine"]),
    "peptic ulcer disease": ("Gastroenterology", []),
    "jaundice": ("Gastroenterology", ["General Medicine"]),
    "migraine": ("Neurology", []),
}


def main() -> None:
    names = set(specialty_names())
    for expected, alternatives in DIAGNOSIS_TO_SPECIALTY.values():
        unknown = {expected, *alternatives} - names
        if unknown:
            raise ValueError(f"Not in specialties.csv: {unknown}")

    with urllib.request.urlopen(URL, timeout=60) as response:
        rows = [json.loads(line) for line in response.read().decode("utf-8").splitlines() if line]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["query_id", "query", "expected_specialty", "acceptable_alternatives",
                         "case_type", "source", "reviewed_by"])
        for index, row in enumerate(rows, start=1):
            diagnosis = row["output_text"].strip().lower()
            expected, alternatives = DIAGNOSIS_TO_SPECIALTY[diagnosis]
            writer.writerow([f"G{index:03d}", row["input_text"].strip(), expected,
                             ";".join(alternatives), f"gretel:{diagnosis}",
                             "gretelai/symptom_to_diagnosis test split (Apache-2.0)", ""])
    print(f"Wrote {len(rows)} rows to {OUT}")


if __name__ == "__main__":
    main()
