# Report-extraction metric 20261113_162049_report_extraction

23 readable synthetic reports · 85 critical details · model openai/gpt-6-luna

Match rule: one phrase covers ≥ 50% of the detail's words (abbreviations and close spellings count) or the same letters ignoring spaces.

## Where details survive

| Level | All details | Decisive details |
|---|---|---|
| A1 in the PDF text | 100% | – |
| A2 still there after the 6,000-character cut | 96% | 94% |
| B returned by the evidence LLM | 93% | 94% |
| C kept after the code check (used by the voters and Step 2) | 93% | 94% |

## By type (kept, level C)

| Type | Details | Kept | LLM returned |
|---|---|---|---|
| body part | 2 | 100% | 100% |
| diagnosis | 28 | 96% | 96% |
| finding | 41 | 93% | 93% |
| procedure | 14 | 86% | 86% |

## Where the missing details were lost

- LLM did not return it: 3
- 6,000-character cut: 3

Cases where every decisive detail was lost: L04
Phrases dropped by the code check (not in the text): 1 · extra phrases kept that are not a critical detail: 39 · speciality correct: 96%

## Per case

| Case | Layout | Kept | Decisive kept | Missed | Extra phrases kept | Speciality |
|---|---|---|---|---|---|---|
| R01 | core report | 3/3 | 2/2 | – | 70% mid stenosis, CORONARY ANGIOGRAPHY, LCx, RCA | Cardiothoracic Surgery |
| R02 | core report | 3/3 | 1/1 | – | – | Orthopaedics |
| R03 | core report | 4/4 | 1/1 | – | – | Oncology |
| R04 | core report | 5/5 | 2/2 | – | – | Nephrology |
| R05 | core report | 3/3 | 2/2 | – | eyes, right eye | Ophthalmology |
| R06 | core report | 4/4 | 1/1 | – | – | Pediatric Cardiology |
| R07 | core report | 5/5 | 2/2 | – | CT scan, CT ABDOMEN, abdomen | Gastroenterology |
| R08 | core report | 3/4 | 1/1 | FNAC (LLM did not return it) | NECK | Oncology |
| R09 | core report | 4/4 | 2/2 | – | HSG, fertility | Reproductive Medicine |
| R10 | core report | 2/2 | 1/1 | – | – | ENT |
| R11 | core report | 2/3 | 2/2 | Ficat stage IV (LLM did not return it) | – | Orthopaedics |
| R12 | core report | 4/4 | 2/2 | – | heart, echo | Cardiology |
| R13 | core report | 2/2 | 1/1 | – | MRI BRAIN W/ CONTRAST, Neurosurgica1 opinion, BRAIN | Neurosurgery |
| R14 | core report | 4/4 | 2/2 | – | UGI ENDOSCOPY, endoscopy | Gastroenterology |
| R15 | core report | 4/4 | 2/2 | – | USG pelvis, Endometrium | Obstetrics & Gynaecology |
| L01 | letterhead noise | 4/4 | 1/1 | – | grade 2, oncology, urology | Oncology |
| L02 | lab table | 5/5 | 2/2 | – | Haemoglobin, Blood urea, Potassium, Calcium, Phosphorus | Nephrology |
| L03 | two columns | 3/3 | 1/1 | – | – | Orthopaedics |
| L04 | long report | 0/3 | 0/2 | triple vessel coronary artery disease (6,000-character cut); coronary artery bypass grafting (6,000-character cut); LAD 90% (6,000-character cut) | – | clarification_required ✗ |
| L05 | typos | 4/4 | 1/1 | – | MRI BRAIN W/ CONTRAST, Neurosurgica1 opinion, BRAIN | Neurosurgery |
| L06 | privacy | 4/4 | 2/2 | – | heart, echo | Cardiology |
| L07 | two reports, one relevant | 3/4 | 1/1 | Bethesda category V (LLM did not return it) | USG NECK, COMPLETE BLOOD COUNT, NECK | Oncology |
| L08 | report only | 4/4 | 2/2 | – | HSG, fertility | Reproductive Medicine |
