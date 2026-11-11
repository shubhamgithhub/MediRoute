# Step 1 benchmark: 20261111_144211_step1_benchmark_ollama

LLM `ollama:llama3.2` · gold sets core50, mediroute, gretel · 346 queries · started 2026-11-11T14:42:11

**Acceptable** = the expected speciality or a listed alternative. A system that does not answer (OURS asks a clarification question, a voter abstains) counts as not acceptable here, so OURS is measured before the patient answers. **Confidently wrong** = answered with an unacceptable speciality. CI = Wilson 95% interval.

## core50 (n=50)

| System | Acceptable (95% CI) | Exact | Top-3 | Answered | Precision when answered | Confidently wrong | Macro-F1 | p50 ms |
|---|---|---|---|---|---|---|---|---|
| B0 most common speciality | 12% (6%–24%) | 10% | 10% | 100% | 12% | 88% | 0.01 | 0 |
| B1 keyword rules | 72% (58%–82%) | 66% | 74% | 76% | 95% | 4% | 0.69 | 1 |
| B2 lookup, keyword (TF-IDF) | 86% (74%–93%) | 74% | 86% | 100% | 86% | 14% | 0.73 | 17 |
| B3 lookup, semantic (embeddings) | 92% (81%–97%) | 78% | 92% | 100% | 92% | 8% | 0.77 | 34 |
| B4 LLM only | 76% (63%–86%) | 72% | 88% | 92% | 83% | 16% | 0.74 | — |
| A1 V1 on LLM evidence | 82% (69%–90%) | 78% | 84% | 92% | 89% | 10% | 0.79 | — |
| A2 V2 on LLM evidence | 86% (74%–93%) | 78% | 86% | 92% | 94% | 6% | 0.77 | — |
| A3 pipeline without LLM | 64% (50%–76%) | 60% | 72% | 68% | 94% | 4% | 0.65 | 45 |
| OURS full pipeline | 80% (67%–89%) | 78% | 86% | 82% | 98% | 2% | 0.80 | 10911 |

OURS against each system, same queries (McNemar exact test on acceptable):

| Compared with | Only OURS right | Only the other right | p-value |
|---|---|---|---|
| B0 most common speciality | 35 | 1 | 0.0 |
| B1 keyword rules | 8 | 4 | 0.3877 |
| B2 lookup, keyword (TF-IDF) | 2 | 5 | 0.4531 |
| B3 lookup, semantic (embeddings) | 1 | 7 | 0.0703 |
| B4 LLM only | 4 | 2 | 0.6875 |
| A1 V1 on LLM evidence | 1 | 2 | 1.0 |
| A2 V2 on LLM evidence | 0 | 3 | 0.25 |
| A3 pipeline without LLM | 9 | 1 | 0.0215 |

OURS full pipeline: decisions {'majority': 41, 'clarification_required': 9}, clarification rate 18%, right speciality among the candidates when it asked: 44%, vague cases asked 4/5, clear cases answered correctly 39/45

A3 pipeline without LLM: decisions {'majority': 34, 'clarification_required': 16}, clarification rate 32%, right speciality among the candidates when it asked: 19%, vague cases asked 5/5, clear cases answered correctly 32/45

Evidence extraction, OURS full pipeline: critical-detail recall 71% (omission 29%); by kind {'body_part': '28/45 (62%)', 'condition': '32/47 (68%)', 'procedure': '28/32 (88%)'}

Evidence extraction, A3 pipeline without LLM: critical-detail recall 31% (omission 69%); by kind {'body_part': '13/45 (29%)', 'condition': '12/47 (26%)', 'procedure': '13/32 (41%)'}

Emergency rules: caught 3/3 emergencies, 0 false alarms in 47 non-emergencies

## mediroute (n=84)

| System | Acceptable (95% CI) | Exact | Top-3 | Answered | Precision when answered | Confidently wrong | Macro-F1 | p50 ms |
|---|---|---|---|---|---|---|---|---|
| B0 most common speciality | 11% (6%–19%) | 5% | 5% | 100% | 11% | 89% | 0.00 | 0 |
| B1 keyword rules | 88% (80%–93%) | 83% | 89% | 90% | 97% | 2% | 0.88 | 1 |
| B2 lookup, keyword (TF-IDF) | 88% (80%–93%) | 83% | 96% | 100% | 88% | 12% | 0.84 | 16 |
| B3 lookup, semantic (embeddings) | 87% (78%–92%) | 71% | 96% | 100% | 87% | 13% | 0.69 | 30 |
| B4 LLM only | 81% (71%–88%) | 75% | 90% | 99% | 82% | 18% | 0.73 | — |
| A1 V1 on LLM evidence | 93% (85%–97%) | 83% | 98% | 100% | 93% | 7% | 0.82 | — |
| A2 V2 on LLM evidence | 93% (85%–97%) | 81% | 98% | 100% | 93% | 7% | 0.79 | — |
| A3 pipeline without LLM | 82% (73%–89%) | 75% | 89% | 84% | 97% | 2% | 0.80 | 47 |
| OURS full pipeline | 89% (81%–94%) | 80% | 99% | 92% | 97% | 2% | 0.80 | 10795 |

OURS against each system, same queries (McNemar exact test on acceptable):

| Compared with | Only OURS right | Only the other right | p-value |
|---|---|---|---|
| B0 most common speciality | 66 | 0 | 0.0 |
| B1 keyword rules | 6 | 5 | 1.0 |
| B2 lookup, keyword (TF-IDF) | 6 | 5 | 1.0 |
| B3 lookup, semantic (embeddings) | 6 | 4 | 0.7539 |
| B4 LLM only | 12 | 5 | 0.1435 |
| A1 V1 on LLM evidence | 1 | 4 | 0.375 |
| A2 V2 on LLM evidence | 1 | 4 | 0.375 |
| A3 pipeline without LLM | 8 | 2 | 0.1094 |

OURS full pipeline: decisions {'majority': 77, 'clarification_required': 7}, clarification rate 8%, right speciality among the candidates when it asked: 86%

A3 pipeline without LLM: decisions {'clarification_required': 13, 'majority': 71}, clarification rate 16%, right speciality among the candidates when it asked: 38%

## gretel (n=212)

| System | Acceptable (95% CI) | Exact | Top-3 | Answered | Precision when answered | Confidently wrong | Macro-F1 | p50 ms |
|---|---|---|---|---|---|---|---|---|
| B0 most common speciality | 72% (66%–78%) | 32% | 32% | 100% | 72% | 28% | 0.05 | 0 |
| B1 keyword rules | 45% (39%–52%) | 30% | 50% | 83% | 55% | 38% | 0.32 | 2 |
| B2 lookup, keyword (TF-IDF) | 68% (62%–74%) | 51% | 67% | 100% | 68% | 32% | 0.53 | 27 |
| B3 lookup, semantic (embeddings) | 73% (67%–79%) | 58% | 71% | 100% | 73% | 27% | 0.54 | 50 |
| B4 LLM only | 73% (66%–78%) | 52% | 81% | 99% | 73% | 26% | 0.44 | — |
| A1 V1 on LLM evidence | 53% (46%–59%) | 42% | 53% | 99% | 54% | 46% | 0.44 | — |
| A2 V2 on LLM evidence | 57% (51%–64%) | 45% | 55% | 99% | 58% | 42% | 0.47 | — |
| A3 pipeline without LLM | 37% (31%–44%) | 25% | 35% | 69% | 53% | 32% | 0.30 | 54 |
| OURS full pipeline | 54% (48%–61%) | 44% | 57% | 88% | 62% | 34% | 0.48 | 13704 |

OURS against each system, same queries (McNemar exact test on acceptable):

| Compared with | Only OURS right | Only the other right | p-value |
|---|---|---|---|
| B0 most common speciality | 48 | 86 | 0.0013 |
| B1 keyword rules | 36 | 17 | 0.0127 |
| B2 lookup, keyword (TF-IDF) | 12 | 42 | 0.0001 |
| B3 lookup, semantic (embeddings) | 10 | 50 | 0.0 |
| B4 LLM only | 18 | 57 | 0.0 |
| A1 V1 on LLM evidence | 6 | 3 | 0.5078 |
| A2 V2 on LLM evidence | 4 | 11 | 0.1185 |
| A3 pipeline without LLM | 44 | 7 | 0.0 |

OURS full pipeline: decisions {'majority': 186, 'clarification_required': 26}, clarification rate 12%, right speciality among the candidates when it asked: 31%

A3 pipeline without LLM: decisions {'majority': 147, 'clarification_required': 65}, clarification rate 31%, right speciality among the candidates when it asked: 15%

## OURS confidently wrong (all sets)

| Set | ID | Expected | OURS | Evidence | Votes |
|---|---|---|---|---|---|
| core50 | C026 | Pediatric Cardiology | Cardiology | perimembranous VSD; pulmonary hypertension; Surgical closure; echo; my daughter | {'V1': 'Cardiology', 'V2': 'Cardiology', 'V3': 'Cardiology'} |
| mediroute | Q031 | Urology | Orthopaedics | kidney stone; severe pain on one side of back | {'V1': 'Orthopaedics', 'V2': 'Orthopaedics', 'V3': 'Urology'} |
| mediroute | Q082 | Endocrinology | Gastroenterology | ulcer; diabetic | {'V1': 'Gastroenterology', 'V2': 'Gastroenterology', 'V3': None} |
| gretel | G003 | General Medicine | Neurology | headaches; migraines | {'V1': 'Neurology', 'V2': 'Neurology', 'V3': 'Neurology'} |
| gretel | G004 | Pulmonology | Cardiology | sweating a lot; can't catch my breath; throat full of phlegm; heart racing; chest hurts; c | {'V1': 'Cardiology', 'V2': 'Pulmonology', 'V3': 'Cardiology'} |
| gretel | G013 | General Medicine | Neurology | fever; chills; nausea; headache; muscle ache | {'V1': 'Neurology', 'V2': 'Neurology', 'V3': 'General Medicine'} |
| gretel | G016 | General Medicine | Neurology | feverish; chilly; sweating; headache; nauseous | {'V1': 'Neurology', 'V2': 'Neurology', 'V3': 'General Medicine'} |
| gretel | G019 | Endocrinology | Neurology | tingling | {'V1': 'Neurology', 'V2': 'Neurology', 'V3': 'General Medicine'} |
| gretel | G020 | Gastroenterology | Dermatology | itchy all over; tired; yellow skin; yellow pee; stomach | {'V1': 'Dermatology', 'V2': 'Dermatology', 'V3': 'Gastroenterology'} |
| gretel | G021 | Neurology | Gastroenterology | headaches; nausea; vomiting; sensitivity to light; sensitivity to sound; left side of head | {'V1': 'Gastroenterology', 'V2': 'Gastroenterology', 'V3': 'Neurology'} |
| gretel | G022 | General Medicine | Neurology | high fever; severe itching; headache; nauseous; muscle aches | {'V1': 'Neurology', 'V2': 'Neurology', 'V3': 'General Medicine'} |
| gretel | G024 | General Medicine | Gastroenterology | high fever; chills; nausea; intense scratching | {'V1': 'Gastroenterology', 'V2': 'Gastroenterology', 'V3': 'General Medicine'} |
| gretel | G028 | General Medicine | Ophthalmology | sleeping trouble; eyes; tired | {'V1': 'Ophthalmology', 'V2': 'Ophthalmology', 'V3': 'General Medicine'} |
| gretel | G031 | General Medicine | Neurology | high fever; headache; chills; terrible pain in belly area; tired | {'V1': 'Neurology', 'V2': 'Neurology', 'V3': 'General Medicine'} |
| gretel | G033 | Pulmonology | Cardiology | sweating; phlegm; coughing up mucus; heart; throat; chest | {'V1': 'Cardiology', 'V2': 'Cardiology', 'V3': 'Pulmonology'} |
| gretel | G039 | General Medicine | Neurology | stomach ache; feverish; chills; headache | {'V1': 'Neurology', 'V2': 'Neurology', 'V3': 'Gastroenterology'} |
| gretel | G041 | General Medicine | Pulmonology | cold; coughing; chest hurts; nose; muscles | {'V1': 'Pulmonology', 'V2': 'Pulmonology', 'V3': 'General Medicine'} |
| gretel | G042 | Cardiology | Neurology | headache; chest pain; dizziness; temples | {'V1': 'Neurology', 'V2': 'Neurology', 'V3': 'Cardiology'} |
| gretel | G044 | Dermatology | ENT | sores; yellow discharge; nose; face; lips | {'V1': 'ENT', 'V2': 'ENT', 'V3': 'Dermatology'} |
| gretel | G045 | Neurology | Ophthalmology | visual disturbances; headaches; vision | {'V1': 'Ophthalmology', 'V2': 'Ophthalmology', 'V3': 'Ophthalmology'} |
| gretel | G047 | Endocrinology | Pulmonology | trouble breathing; yeast infections | {'V1': 'Pulmonology', 'V2': 'Pulmonology', 'V3': 'Pulmonology'} |
| gretel | G050 | General Medicine | Gastroenterology | vomiting; stomach pains; dizziness; arms; back; neck | {'V1': 'Gastroenterology', 'V2': 'Gastroenterology', 'V3': 'Gastroenterology'} |
| gretel | G055 | General Medicine | Neurology | fever; chills; vomiting; sweating; headache; nauseous | {'V1': 'Neurology', 'V2': 'Neurology', 'V3': 'General Medicine'} |
| gretel | G056 | Gastroenterology | Dermatology | itching; nausea; fatigue; fever; rash; stomach | {'V1': 'Dermatology', 'V2': 'Dermatology', 'V3': 'General Medicine'} |
| gretel | G057 | General Medicine | Neurology | high fever; severe itching; chills; vomiting; headache | {'V1': 'Neurology', 'V2': 'Neurology', 'V3': 'General Medicine'} |
| gretel | G058 | General Medicine | Pulmonology | coughing a lot; trouble breathing; throat hurts; phlegm in chest; running nose | {'V1': 'Pulmonology', 'V2': 'Pulmonology', 'V3': 'Pulmonology'} |
| gretel | G063 | Cardiothoracic Surgery | Bariatric Surgery | prominent blood vessels on my calves; overweight | {'V1': 'Bariatric Surgery', 'V2': 'Bariatric Surgery', 'V3': 'Cardiology'} |
| gretel | G064 | General Medicine | Pulmonology | run down; feble; throat hurts; nasty cough; chills; high temperature | {'V1': 'Pulmonology', 'V2': 'Pulmonology', 'V3': 'General Medicine'} |
| gretel | G065 | Gastroenterology | Neurology | chronic bad breath; sour taste in mouth; tingling sensation in throat | {'V1': 'Neurology', 'V2': 'Neurology', 'V3': 'General Medicine'} |
| gretel | G069 | Endocrinology | Ophthalmology | lost sight | {'V1': 'Ophthalmology', 'V2': 'Ophthalmology', 'V3': 'General Medicine'} |
| gretel | G071 | General Medicine | Ophthalmology | cold; red eyes; tired; drained; phlegm in throat; sinuses; lymph nodes | {'V1': 'Ophthalmology', 'V2': 'Ophthalmology', 'V3': 'General Medicine'} |
| gretel | G076 | General Medicine | Psychiatry | pain in lymph nodes; rashes all over body; cannot sleep | {'V1': 'Psychiatry', 'V2': 'Psychiatry', 'V3': 'Hematology & Bone Marrow Transplant'} |
| gretel | G078 | General Medicine | Pulmonology | trouble breathing; nauseous; mild belly pain | {'V1': 'Pulmonology', 'V2': 'Gastroenterology', 'V3': 'Pulmonology'} |
| gretel | G079 | Gastroenterology | ENT | trouble swallowing food; throat feels like it's closing up; bad taste in mouth | {'V1': 'ENT', 'V2': 'ENT', 'V3': 'ENT'} |
| gretel | G083 | General Medicine | Ophthalmology | red skin; itchy skin; headaches; runny eyes; cheeks; lips | {'V1': 'Ophthalmology', 'V2': 'Ophthalmology', 'V3': 'Dermatology'} |
| gretel | G090 | General Medicine | Ophthalmology | itchy swollen skin; headaches; watery eyes; cheeks; lips | {'V1': 'Ophthalmology', 'V2': 'Ophthalmology', 'V3': 'Dermatology'} |
| gretel | G091 | Cardiology | Neurology | headaches; chest pains; dizziness; lack of balance | {'V1': 'Neurology', 'V2': 'Neurology', 'V3': 'Cardiology'} |
| gretel | G092 | General Medicine | Pulmonology | bad cold; coughing up phlegm; chest hurts; can't smell anything; muscles | {'V1': 'Pulmonology', 'V2': 'Pulmonology', 'V3': 'General Medicine'} |
| gretel | G093 | General Medicine | Neurology | itchy all over body; chills; nausea; sweating; high fever; headache | {'V1': 'Neurology', 'V2': 'Neurology', 'V3': 'General Medicine'} |
| gretel | G095 | General Medicine | Pulmonology | asthma; wheezing; breathing issues; fevers; headaches; tired | {'V1': 'Pulmonology', 'V2': 'Pulmonology', 'V3': 'Pulmonology'} |
| gretel | G097 | General Medicine | Neurology | severe fever; headache; pain behind eyes; tired | {'V1': 'Neurology', 'V2': 'Neurology', 'V3': 'General Medicine'} |
| gretel | G098 | General Medicine | Neurology | fever; headache; tired all the time | {'V1': 'Neurology', 'V2': 'Neurology', 'V3': 'General Medicine'} |
| gretel | G099 | Endocrinology | Dermatology | skin irritations; rashes; skin bruises; skin cuts; crevices | {'V1': 'Dermatology', 'V2': 'Dermatology', 'V3': 'Dermatology'} |
| gretel | G101 | Neurology | Ophthalmology | headaches; nauseous; blurred vision | {'V1': 'Ophthalmology', 'V2': 'Ophthalmology', 'V3': 'Neurology'} |
| gretel | G102 | Cardiology | Neurology | headache; chest pain; dizziness; trouble concentrating | {'V1': 'Neurology', 'V2': 'Neurology', 'V3': 'Neurology'} |
| gretel | G107 | Endocrinology | Dermatology | rashes; skin irritations; skin bruises; skin cuts; crevices | {'V1': 'Dermatology', 'V2': 'Dermatology', 'V3': 'Dermatology'} |
| gretel | G110 | Gastroenterology | ENT | sore throat; scratchy voice; bad breath | {'V1': 'ENT', 'V2': 'ENT', 'V3': 'ENT'} |
| gretel | G112 | General Medicine | Dermatology | rash; vomiting; itchy; body; joints | {'V1': 'Dermatology', 'V2': 'Dermatology', 'V3': 'Dermatology'} |
| gretel | G113 | Neurology | Gastroenterology | headaches; digestive issues; acid reflux; indigestion; sore neck; depression | {'V1': 'Gastroenterology', 'V2': 'Gastroenterology', 'V3': 'Gastroenterology'} |
| gretel | G121 | General Medicine | Neurology | fever; chills; vomiting; headache; sweating; nauseous | {'V1': 'Neurology', 'V2': 'Neurology', 'V3': 'General Medicine'} |
| gretel | G124 | Cardiology | Neurology | headache; chest | {'V1': 'Neurology', 'V2': 'Neurology', 'V3': 'Cardiology'} |
| gretel | G129 | General Medicine | Ophthalmology | itchy red skin; face puffing; lips puffing; watery eyes; headaches | {'V1': 'Ophthalmology', 'V2': 'Ophthalmology', 'V3': 'Dermatology'} |
| gretel | G134 | General Medicine | Neurology | metallic taste in mouth; changed sense of taste; changed sense of smell; muscle aches; joi | {'V1': 'Neurology', 'V2': 'Neurology', 'V3': 'Oncology'} |
| gretel | G135 | General Medicine | Neurology | high fever; severe itching; headache; nauseous | {'V1': 'Neurology', 'V2': 'Neurology', 'V3': 'General Medicine'} |
| gretel | G136 | Endocrinology | ENT | dry mouth; dry throat | {'V1': 'ENT', 'V2': 'ENT', 'V3': 'General Medicine'} |
| gretel | G139 | Urology | Gastroenterology | lower abdomen pain; low body temperature | {'V1': 'Gastroenterology', 'V2': 'Gastroenterology', 'V3': 'Gastroenterology'} |
| gretel | G146 | General Medicine | Pulmonology | sneezing a lot; tired; throat hurts; mucus in nose and throat; swollen and puffy neck | {'V1': 'Pulmonology', 'V2': 'Pulmonology', 'V3': 'General Medicine'} |
| gretel | G148 | Cardiology | Neurology | headache; chest pain; dizziness; balance | {'V1': 'Neurology', 'V2': 'Neurology', 'V3': 'Cardiology'} |
| gretel | G150 | Cardiology | Neurology | headache; chest pain; dizziness | {'V1': 'Neurology', 'V2': 'Neurology', 'V3': 'Cardiology'} |
| gretel | G154 | General Medicine | Neurology | scratching a lot; chills; vomiting; fever; headache; nauseous | {'V1': 'Neurology', 'V2': 'Neurology', 'V3': 'General Medicine'} |
| gretel | G161 | General Medicine | Neurology | severe headache; pain behind eyes; fatigue; tired | {'V1': 'Ophthalmology', 'V2': 'Neurology', 'V3': 'Neurology'} |
| gretel | G167 | General Medicine | Orthopaedics | metallic taste in mouth; severe joint pain; muscle pain | {'V1': 'Orthopaedics', 'V2': 'Orthopaedics', 'V3': 'Oncology'} |
| gretel | G171 | Cardiothoracic Surgery | Orthopaedics | pain in calves; visible blood vessels; periods; legs | {'V1': 'Orthopaedics', 'V2': 'Orthopaedics', 'V3': 'Cardiology'} |
| gretel | G177 | General Medicine | Ophthalmology | runny nose; sneezing; itchy eyes; watery eyes; coughing; head hurt; tired | {'V1': 'Ophthalmology', 'V2': 'Ophthalmology', 'V3': 'ENT'} |
| gretel | G178 | Gastroenterology | Oncology | constant sour taste in mouth; lump in throat; hiccups | {'V1': 'Oncology', 'V2': 'Oncology', 'V3': 'General Medicine'} |
| gretel | G182 | Cardiology | Neurology | headaches; dizziness | {'V1': 'Neurology', 'V2': 'Neurology', 'V3': 'Neurology'} |
| gretel | G185 | Pulmonology | Cardiology | trouble breathing; chest hurts; heart racing; coughing up dark mucus; sweating a lot; full | {'V1': 'Cardiology', 'V2': 'Cardiology', 'V3': 'Cardiology'} |
| gretel | G189 | Neurology | Gastroenterology | eyesight problems; acid reflux; indigestion; headaches; migraines; neck | {'V1': 'Gastroenterology', 'V2': 'Gastroenterology', 'V3': 'Ophthalmology'} |
| gretel | G193 | Endocrinology | ENT | dry mouth; dry throat | {'V1': 'ENT', 'V2': 'ENT', 'V3': 'Endocrinology'} |
| gretel | G194 | Neurology | Gastroenterology | headaches; nausea; sensitivity to light | {'V1': 'Gastroenterology', 'V2': 'Gastroenterology', 'V3': 'Neurology'} |
| gretel | G201 | Gastroenterology | Dermatology | itchy all over; yellow skin; fever; stomach | {'V1': 'Dermatology', 'V2': 'Dermatology', 'V3': 'General Medicine'} |
| gretel | G204 | General Medicine | Gastroenterology | nausea; chest hurts | {'V1': 'Gastroenterology', 'V2': 'Gastroenterology', 'V3': 'Cardiology'} |
| gretel | G208 | General Medicine | Orthopaedics | muscle pain; vomiting; back pain; tired; legs | {'V1': 'Orthopaedics', 'V2': 'Orthopaedics', 'V3': 'General Medicine'} |
| gretel | G212 | General Medicine | Neurology | severe headache; pressure in head; mild fever; small red spots; back | {'V1': 'Dermatology', 'V2': 'Neurology', 'V3': 'Neurology'} |
