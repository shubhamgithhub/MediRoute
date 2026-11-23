# Portal top-5 metrics — 20261122_221042_hospitals

Good = NABH-scope treatment grade ≥ 2 + NABH accredited and valid on 2026-11-22 + same city/area or same state. No old grades used. 45 queries (data/evaluation/step2_gold.csv); 1 have no good hospital in our data (S4-07) and are left out of P@5 / NDCG@5 / Hit@1 (Bad@5 counts all).

| System | P@5 | NDCG@5 | Hit@1 | Bad@5 | MaxP@5 |
|---|---|---|---|---|---|
| Portal end to end (patient text → Step 1 → Step 2) | 0.67 [0.60–0.74] | 0.68 [0.60–0.76] | 0.77 | 0.24 | 0.94 |
| Engine given the gold speciality + procedure (no Step 1) | 0.66 [0.59–0.73] | 0.66 [0.59–0.74] | 0.77 | 0.31 | 0.94 |
| B0 random among eligible (20 seeds) | 0.54 [0.47–0.60] | 0.54 [0.47–0.61] | 0.59 | 0.16 | 0.94 |

Paired permutation test, portal vs B0: P@5 p = 0.000, NDCG@5 p = 0.000; portal vs reference: P@5 p = 0.558, NDCG@5 p = 0.204.

## By group (portal / reference / B0)

| Group | Queries | P@5 | NDCG@5 | Hit@1 | Bad@5 |
|---|---|---|---|---|---|
| Big cities and states (S1–S3) | 30 | 0.78 / 0.75 / 0.64 | 0.71 / 0.69 / 0.57 | 0.77 / 0.77 / 0.61 | 0.17 / 0.27 / 0.23 |
| Rare specialities (S5) | 7 | 0.43 / 0.46 / 0.24 | 0.35 / 0.36 / 0.23 | 0.71 / 0.71 / 0.49 | 0.71 / 0.71 / 0.06 |
| Small cities (S4) | 8 | 0.46 / 0.46 / 0.40 | 0.87 / 0.87 / 0.74 | 0.86 / 0.86 / 0.61 | 0.12 / 0.12 / 0.00 |

## Why shown hospitals were not good (portal top 5)

| Reason | Times |
|---|---|
| treatment unknown (no NABH scope grade) | 39 |
| NABH Needs verification | 22 |
| scope grade 0 | 13 |
| NABH Not found in NABH directory | 11 |
| outside city and state | 11 |
| NABH certificate expired | 5 |
| scope grade 1 | 2 |

## Per query (portal)

| Query | Need | Location | Good exist | P@5 | NDCG@5 | Hit@1 | Bad@5 |
|---|---|---|---|---|---|---|---|
| S1-01 | Neurology | - | Hyderabad | 8 | 0.80 | 0.79 | 1.00 | 0.00 |
| S1-02 | Oncology | - | Mumbai | 24 | 0.60 | 0.51 | 0.00 | 0.00 |
| S1-03 | Orthopaedics | - | Delhi NCR | 13 | 0.80 | 0.79 | 1.00 | 1.00 |
| S1-04 | Gastroenterology | - | Chennai | 10 | 0.80 | 0.87 | 1.00 | 0.00 |
| S1-05 | Nephrology | - | Kolkata | 9 | 0.80 | 0.87 | 1.00 | 0.00 |
| S1-06 | Cardiology | - | Bengaluru | 7 | 0.80 | 0.66 | 0.00 | 1.00 |
| S1-07 | Neurosurgery | - | Mumbai | 24 | 1.00 | 1.00 | 1.00 | 0.00 |
| S1-08 | Obstetrics & Gynaecology | - | Delhi NCR | 14 | 0.80 | 0.66 | 0.00 | 1.00 |
| S1-09 | Pulmonology | - | Chennai | 10 | 0.80 | 0.87 | 1.00 | 0.00 |
| S1-10 | Urology | - | Hyderabad | 8 | 1.00 | 1.00 | 1.00 | 0.00 |
| S2-01 | Cardiothoracic Surgery | heart bypass surgery | Chennai | 10 | 0.60 | 0.64 | 1.00 | 0.00 |
| S2-02 | Cardiology | valve replacement through a catheter | Mumbai | 25 | 0.80 | 0.58 | 1.00 | 0.00 |
| S2-03 | Organ Transplant | kidney transplant | Chennai | 10 | 0.80 | 0.83 | 1.00 | 0.00 |
| S2-04 | Hematology & Bone Marrow Transplant | bone marrow transplant | Delhi NCR | 9 | 0.40 | 0.23 | 0.00 | 1.00 |
| S2-05 | Orthopaedics | knee replacement | Kolkata | 8 | 0.80 | 0.79 | 1.00 | 0.00 |
| S2-06 | Cardiology | stent | Hyderabad | 8 | 0.80 | 0.75 | 1.00 | 0.00 |
| S2-07 | Organ Transplant | living donor liver transplant | Delhi NCR | 12 | 0.40 | 0.22 | 0.00 | 0.00 |
| S2-08 | Oncology | radiation therapy | Bengaluru | 8 | 1.00 | 1.00 | 1.00 | 0.00 |
| S2-09 | Nephrology | dialysis | Mumbai | 24 | 0.60 | 0.68 | 1.00 | 0.00 |
| S2-10 | Neurosurgery | brain tumour surgery | Delhi NCR | 15 | 1.00 | 1.00 | 1.00 | 0.00 |
| S2-11 | Urology | robotic prostate removal | Mumbai | 25 | 1.00 | 0.67 | 1.00 | 0.00 |
| S2-12 | Neurosurgery | deep brain stimulation | Hyderabad | 8 | 0.80 | 0.85 | 1.00 | 0.00 |
| S3-01 | Orthopaedics | knee replacement | Maharashtra | 24 | 1.00 | 0.90 | 1.00 | 0.00 |
| S3-02 | Cardiothoracic Surgery | heart bypass surgery | Tamil Nadu | 10 | 0.60 | 0.70 | 1.00 | 0.00 |
| S3-03 | Organ Transplant | kidney transplant | Karnataka | 7 | 0.80 | 0.90 | 1.00 | 0.00 |
| S3-04 | Oncology | chemotherapy | Kerala | 7 | 0.80 | 0.66 | 0.00 | 0.00 |
| S3-05 | Organ Transplant | liver transplant | anywhere | 90 | 0.80 | 0.71 | 1.00 | 0.00 |
| S3-06 | Cardiothoracic Surgery | heart transplant | anywhere | 102 | 0.80 | 0.37 | 0.00 | 0.00 |
| S3-07 | Cardiology | valve replacement through a catheter | anywhere | 110 | 0.80 | 0.66 | 1.00 | 0.00 |
| S3-08 | Hematology & Bone Marrow Transplant | bone marrow transplant | anywhere | 76 | 0.60 | 0.28 | 1.00 | 1.00 |
| S4-01 | Cardiology | - | Jaipur | 3 | 0.60 | 1.00 | 1.00 | 0.00 |
| S4-02 | Oncology | - | Patna | 2 | 0.20 | 0.39 | 0.00 | 0.00 |
| S4-03 | Orthopaedics | - | Bhubaneswar | 1 | 0.20 | 1.00 | 1.00 | 0.00 |
| S4-04 | Neurology | - | Indore | 4 | 0.60 | 0.94 | 1.00 | 0.00 |
| S4-05 | Nephrology | - | Coimbatore | 10 | 0.40 | 0.79 | 1.00 | 0.00 |
| S4-06 | Gastroenterology | - | Lucknow | 3 | 0.60 | 0.95 | 1.00 | 0.00 |
| S4-07 | Cardiology | - | Guwahati | 0 | – | – | – | 1.00 |
| S4-08 | Orthopaedics | knee replacement | Jaipur | 3 | 0.60 | 1.00 | 1.00 | 0.00 |
| S5-01 | Dermatology | - | Kochi | 8 | 0.00 | 0.00 | 0.00 | 1.00 |
| S5-02 | Reproductive Medicine | IVF | Mumbai | 7 | 0.20 | 0.10 | 0.00 | 1.00 |
| S5-03 | Ophthalmology | cataract surgery | Pune | 24 | 0.60 | 0.46 | 1.00 | 1.00 |
| S5-04 | Pediatric Cardiology | hole in the heart repair | anywhere | 59 | 0.60 | 0.45 | 1.00 | 0.00 |
| S5-05 | Bariatric Surgery | weight loss surgery | Ahmedabad | 8 | 0.40 | 0.35 | 1.00 | 1.00 |
| S5-06 | ENT | cochlear implant | Delhi NCR | 13 | 0.40 | 0.26 | 1.00 | 0.00 |
| S5-07 | Neurosurgery | CyberKnife | anywhere | 110 | 0.80 | 0.87 | 1.00 | 1.00 |

Notes: treatment grades are quotes from the NABH scope taken by an LLM and checked by code (grade set by code); hospitals without a scope document (not H-/entry-level PDF on the NABH portal) have unknown treatment. Expiry uses the date printed on the scope document; a renewed certificate would not be seen.
