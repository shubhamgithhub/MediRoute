# Step 1 core gold set: guide for the reviewing doctor

**File:** [step1_gold_core50.csv](step1_gold_core50.csv) · 50 synthetic patient messages ·
**Status:** draft, written by the team, awaiting clinical review

## What MediRoute's Step 1 does

A patient (usually an international patient who already has a diagnosis or reports) types a message
and may attach a report. Step 1 suggests **which speciality to search for** in Indian hospitals. It
does **not** diagnose, advise treatment or judge urgency. Emergencies are caught by fixed rules that
show a "seek emergency care now" message.

## What we ask you to check (about 1–2 hours)

For each row, please check:

1. **`expected_specialty`**: is this the speciality a coordinator should route this patient to?
2. **`acceptable_alternatives`**: are these also reasonable, and is any reasonable one missing?
3. **`critical_details`**: are these the facts that must not be missed (body part, condition,
   procedure)?
4. **`expects_clarification`** (vague cases): is it right that the system should ask a question
   instead of answering?
5. **`emergency`**: should this message trigger the emergency notice?

Then fill in the three review columns:

| Column | What to write |
|--------|---------------|
| `review_status` | `approved`, `corrected` (you changed something) or `rejected` (unrealistic, drop it) |
| `reviewed_by` | Your name and qualification, e.g. "Dr A. Kumar, MD (Medicine)" |
| `review_notes` | Any correction or comment |

## Speciality names to use

Only these names (from `data/medical_taxonomy/specialties.csv`): Cardiology, Cardiothoracic Surgery,
Pediatric Cardiology, Oncology, Hematology & Bone Marrow Transplant, Orthopaedics, Neurology,
Neurosurgery, Gastroenterology, Nephrology, Urology, Organ Transplant, Obstetrics & Gynaecology,
Reproductive Medicine, Paediatrics, Endocrinology, Pulmonology, Plastic & Reconstructive Surgery,
Bariatric Surgery, Emergency Medicine, Critical Care, Ophthalmology, ENT, Dermatology, Psychiatry,
General Medicine.

If the right speciality is not in this list, write it in `review_notes`.

## Column reference

| Column | Meaning |
|--------|---------|
| `query_id` | C001–C050 |
| `query` | What the patient types |
| `report_text` | Text of an attached report, if any (some are deliberately messy: typos, OCR errors, page headers) |
| `expected_specialty` | The one speciality to route to |
| `acceptable_alternatives` | Other specialities also counted correct (`;`-separated) |
| `case_type` | diagnosis · procedure_only · report · noisy_report · cghs_gap (procedure not in the CGHS list) · vague · emergency · paediatric |
| `critical_details` | Facts the system must extract: `body_part=…; condition=…; procedure=…` |
| `expects_clarification` | `true` if the right behaviour is to ask a question |
| `emergency` | `true` if the emergency notice should be shown |
| `source` | `team_synthetic`: written by the team, no real patient data |

All messages are synthetic. No real patient information is included.
