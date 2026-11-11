# Step 1 benchmark: 20261111_144211_step1_benchmark_ollama + method 4 (replay)

LLM `ollama:llama3.2` · gold sets core50, mediroute, gretel · 346 queries · started 2026-11-11T14:42:11

## How to read the metrics

- **Accuracy (P@1)**: the top answer is the expected speciality or a listed alternative. A method that asks a clarification question or abstains counts as not correct, so the pipelines are scored before the patient answers. 95% CI = Wilson interval.
- **Recall@3**: the expected speciality or an alternative is among the top 3 candidates (also when the method asks; the candidates are what it offers).
- **NDCG@3**: ranking quality of the top 3; relevance expected = 2, alternative = 1, other = 0.
- **MRR@3**: 1 / rank of the first acceptable speciality (0 if not in the top 3).
- **Macro precision / recall / F1**: per expected speciality, then averaged, so rare specialities count as much as common ones; strict (expected label only).
- **Confidently wrong**: answered with an unacceptable speciality, the unsafe outcome. **Asks**: share of queries where the pipeline asks a clarification question.

## core50 (n=50)

| Method | Accuracy (95% CI) | Recall@3 | NDCG@3 | MRR@3 | Macro precision | Macro recall | Macro-F1 | Confidently wrong | Asks |
|---|---|---|---|---|---|---|---|---|---|
| 1 Keyword search (TF-IDF) | 86% (74%–93%) | 92% | 0.78 | 0.88 | 0.76 | 0.77 | 0.73 | 14% | — |
| 2 Semantic search (embeddings) | 92% (81%–97%) | 96% | 0.84 | 0.94 | 0.80 | 0.81 | 0.77 | 8% | — |
| 3 LLM only | 76% (63%–86%) | 90% | 0.77 | 0.83 | 0.76 | 0.77 | 0.74 | 16% | — |
| 4 MediRoute: hybrid lookup + LLM | 68% (54%–79%) | 90% | 0.82 | 0.86 | 0.83 | 0.74 | 0.77 | 2% | 30% |
| 4b same, but asks when the LLM abstains | 68% (54%–79%) | 90% | 0.82 | 0.86 | 0.83 | 0.74 | 0.77 | 2% | 30% |
| Before: current pipeline (3 voters) | 80% (67%–89%) | 88% | 0.80 | 0.86 | 0.82 | 0.79 | 0.80 | 2% | 18% |

4 MediRoute: hybrid lookup + LLM against each method, same queries (McNemar exact test on accuracy):

| Compared with | Only it right | Only the other right | p-value |
|---|---|---|---|
| 1 Keyword search (TF-IDF) | 2 | 11 | 0.0225 |
| 2 Semantic search (embeddings) | 1 | 13 | 0.0018 |
| 3 LLM only | 0 | 4 | 0.125 |
| 4b same, but asks when the LLM abstains | 0 | 0 | 1.0 |
| Before: current pipeline (3 voters) | 1 | 7 | 0.0703 |
| B0 most common speciality (floor) | 29 | 1 | 0.0 |
| B1 keyword rules (specialties.csv) | 6 | 8 | 0.7905 |
| A1 keyword search on LLM evidence | 1 | 8 | 0.0391 |
| A2 semantic search on LLM evidence | 1 | 10 | 0.0117 |
| A3 3-voter pipeline without LLM | 8 | 6 | 0.7905 |
| A4 hybrid lookup voter alone, on LLM evidence | 0 | 8 | 0.0078 |

4 MediRoute: hybrid lookup + LLM: decisions {'majority': 35, 'clarification_required': 15}, clarification rate 30%, acceptable speciality among the candidates when it asked: 60%, vague cases asked 5/5, clear cases answered correctly 34/45

4b same, but asks when the LLM abstains: decisions {'majority': 35, 'clarification_required': 15}, clarification rate 30%, acceptable speciality among the candidates when it asked: 60%, vague cases asked 5/5, clear cases answered correctly 34/45

Before: current pipeline (3 voters): decisions {'majority': 41, 'clarification_required': 9}, clarification rate 18%, acceptable speciality among the candidates when it asked: 44%, vague cases asked 4/5, clear cases answered correctly 39/45

Evidence extraction by the LLM (shared by the pipelines): critical-detail recall 71% (omission 29%); by kind {'body_part': '28/45 (62%)', 'condition': '32/47 (68%)', 'procedure': '28/32 (88%)'}

Emergency rules: caught 3/3 emergencies, 0 false alarms in 47 non-emergencies

## mediroute (n=84)

| Method | Accuracy (95% CI) | Recall@3 | NDCG@3 | MRR@3 | Macro precision | Macro recall | Macro-F1 | Confidently wrong | Asks |
|---|---|---|---|---|---|---|---|---|---|
| 1 Keyword search (TF-IDF) | 88% (80%–93%) | 98% | 0.82 | 0.93 | 0.90 | 0.84 | 0.84 | 12% | — |
| 2 Semantic search (embeddings) | 87% (78%–92%) | 98% | 0.82 | 0.92 | 0.74 | 0.71 | 0.69 | 13% | — |
| 3 LLM only | 81% (71%–88%) | 94% | 0.79 | 0.87 | 0.80 | 0.74 | 0.73 | 18% | — |
| 4 MediRoute: hybrid lookup + LLM | 67% (56%–76%) | 99% | 0.86 | 0.94 | 0.81 | 0.63 | 0.69 | 1% | 32% |
| 4b same, but asks when the LLM abstains | 67% (56%–76%) | 99% | 0.86 | 0.94 | 0.82 | 0.63 | 0.70 | 0% | 33% |
| Before: current pipeline (3 voters) | 89% (81%–94%) | 99% | 0.86 | 0.96 | 0.83 | 0.79 | 0.80 | 2% | 8% |

4 MediRoute: hybrid lookup + LLM against each method, same queries (McNemar exact test on accuracy):

| Compared with | Only it right | Only the other right | p-value |
|---|---|---|---|
| 1 Keyword search (TF-IDF) | 5 | 23 | 0.0009 |
| 2 Semantic search (embeddings) | 2 | 19 | 0.0002 |
| 3 LLM only | 0 | 12 | 0.0005 |
| 4b same, but asks when the LLM abstains | 0 | 0 | 1.0 |
| Before: current pipeline (3 voters) | 0 | 19 | 0.0 |
| B0 most common speciality (floor) | 49 | 2 | 0.0 |
| B1 keyword rules (specialties.csv) | 5 | 23 | 0.0009 |
| A1 keyword search on LLM evidence | 1 | 23 | 0.0 |
| A2 semantic search on LLM evidence | 0 | 22 | 0.0 |
| A3 3-voter pipeline without LLM | 5 | 18 | 0.0106 |
| A4 hybrid lookup voter alone, on LLM evidence | 0 | 20 | 0.0 |

4 MediRoute: hybrid lookup + LLM: decisions {'majority': 57, 'clarification_required': 27}, clarification rate 32%, acceptable speciality among the candidates when it asked: 96%

4b same, but asks when the LLM abstains: decisions {'majority': 56, 'clarification_required': 28}, clarification rate 33%, acceptable speciality among the candidates when it asked: 96%

Before: current pipeline (3 voters): decisions {'majority': 77, 'clarification_required': 7}, clarification rate 8%, acceptable speciality among the candidates when it asked: 86%

## gretel (n=212)

| Method | Accuracy (95% CI) | Recall@3 | NDCG@3 | MRR@3 | Macro precision | Macro recall | Macro-F1 | Confidently wrong | Asks |
|---|---|---|---|---|---|---|---|---|---|
| 1 Keyword search (TF-IDF) | 68% (62%–74%) | 85% | 0.60 | 0.76 | 0.58 | 0.50 | 0.53 | 32% | — |
| 2 Semantic search (embeddings) | 73% (67%–79%) | 91% | 0.64 | 0.81 | 0.57 | 0.56 | 0.54 | 27% | — |
| 3 LLM only | 73% (66%–78%) | 94% | 0.73 | 0.83 | 0.58 | 0.46 | 0.44 | 26% | — |
| 4 MediRoute: hybrid lookup + LLM | 34% (28%–41%) | 92% | 0.66 | 0.73 | 0.51 | 0.28 | 0.32 | 7% | 58% |
| 4b same, but asks when the LLM abstains | 34% (28%–41%) | 92% | 0.66 | 0.73 | 0.51 | 0.28 | 0.32 | 7% | 58% |
| Before: current pipeline (3 voters) | 54% (48%–61%) | 76% | 0.49 | 0.65 | 0.60 | 0.49 | 0.48 | 34% | 12% |

4 MediRoute: hybrid lookup + LLM against each method, same queries (McNemar exact test on accuracy):

| Compared with | Only it right | Only the other right | p-value |
|---|---|---|---|
| 1 Keyword search (TF-IDF) | 9 | 81 | 0.0 |
| 2 Semantic search (embeddings) | 5 | 87 | 0.0 |
| 3 LLM only | 0 | 81 | 0.0 |
| 4b same, but asks when the LLM abstains | 0 | 0 | 1.0 |
| Before: current pipeline (3 voters) | 1 | 43 | 0.0 |
| B0 most common speciality (floor) | 40 | 120 | 0.0 |
| B1 keyword rules (specialties.csv) | 18 | 41 | 0.0038 |
| A1 keyword search on LLM evidence | 4 | 43 | 0.0 |
| A2 semantic search on LLM evidence | 3 | 52 | 0.0 |
| A3 3-voter pipeline without LLM | 20 | 25 | 0.5515 |
| A4 hybrid lookup voter alone, on LLM evidence | 0 | 46 | 0.0 |

4 MediRoute: hybrid lookup + LLM: decisions {'majority': 88, 'clarification_required': 124}, clarification rate 58%, acceptable speciality among the candidates when it asked: 76%

4b same, but asks when the LLM abstains: decisions {'majority': 88, 'clarification_required': 124}, clarification rate 58%, acceptable speciality among the candidates when it asked: 76%

Before: current pipeline (3 voters): decisions {'majority': 186, 'clarification_required': 26}, clarification rate 12%, acceptable speciality among the candidates when it asked: 31%

## Appendix: other baselines and ablations

### core50

| Method | Accuracy (95% CI) | Recall@3 | NDCG@3 | MRR@3 | Macro precision | Macro recall | Macro-F1 | Confidently wrong | Asks |
|---|---|---|---|---|---|---|---|---|---|
| B0 most common speciality (floor) | 12% (6%–24%) | 12% | 0.10 | 0.12 | 0.00 | 0.04 | 0.01 | 88% | — |
| B1 keyword rules (specialties.csv) | 72% (58%–82%) | 76% | 0.66 | 0.74 | 0.78 | 0.67 | 0.69 | 4% | — |
| A1 keyword search on LLM evidence | 82% (69%–90%) | 88% | 0.77 | 0.85 | 0.82 | 0.79 | 0.79 | 10% | — |
| A2 semantic search on LLM evidence | 86% (74%–93%) | 90% | 0.80 | 0.88 | 0.79 | 0.79 | 0.77 | 6% | — |
| A3 3-voter pipeline without LLM | 64% (50%–76%) | 74% | 0.66 | 0.72 | 0.71 | 0.63 | 0.65 | 4% | 32% |
| A4 hybrid lookup voter alone, on LLM evidence | 84% (72%–92%) | 88% | 0.79 | 0.86 | 0.84 | 0.83 | 0.81 | 8% | — |

### mediroute

| Method | Accuracy (95% CI) | Recall@3 | NDCG@3 | MRR@3 | Macro precision | Macro recall | Macro-F1 | Confidently wrong | Asks |
|---|---|---|---|---|---|---|---|---|---|
| B0 most common speciality (floor) | 11% (6%–19%) | 11% | 0.06 | 0.11 | 0.00 | 0.04 | 0.00 | 89% | — |
| B1 keyword rules (specialties.csv) | 88% (80%–93%) | 90% | 0.77 | 0.89 | 0.95 | 0.85 | 0.88 | 2% | — |
| A1 keyword search on LLM evidence | 93% (85%–97%) | 99% | 0.84 | 0.95 | 0.83 | 0.83 | 0.82 | 7% | — |
| A2 semantic search on LLM evidence | 93% (85%–97%) | 99% | 0.85 | 0.96 | 0.81 | 0.80 | 0.79 | 7% | — |
| A3 3-voter pipeline without LLM | 82% (73%–89%) | 90% | 0.79 | 0.89 | 0.89 | 0.76 | 0.80 | 2% | 16% |
| A4 hybrid lookup voter alone, on LLM evidence | 90% (82%–95%) | 99% | 0.84 | 0.94 | 0.81 | 0.78 | 0.77 | 10% | — |

### gretel

| Method | Accuracy (95% CI) | Recall@3 | NDCG@3 | MRR@3 | Macro precision | Macro recall | Macro-F1 | Confidently wrong | Asks |
|---|---|---|---|---|---|---|---|---|---|
| B0 most common speciality (floor) | 72% (66%–78%) | 72% | 0.39 | 0.72 | 0.03 | 0.10 | 0.05 | 28% | — |
| B1 keyword rules (specialties.csv) | 45% (39%–52%) | 65% | 0.43 | 0.54 | 0.50 | 0.28 | 0.32 | 38% | — |
| A1 keyword search on LLM evidence | 53% (46%–59%) | 72% | 0.46 | 0.62 | 0.52 | 0.46 | 0.44 | 46% | — |
| A2 semantic search on LLM evidence | 57% (51%–64%) | 73% | 0.48 | 0.65 | 0.62 | 0.49 | 0.47 | 42% | — |
| A3 3-voter pipeline without LLM | 37% (31%–44%) | 54% | 0.34 | 0.48 | 0.49 | 0.26 | 0.30 | 32% | 31% |
| A4 hybrid lookup voter alone, on LLM evidence | 56% (49%–63%) | 71% | 0.47 | 0.63 | 0.59 | 0.49 | 0.47 | 43% | — |

## 4 MediRoute: hybrid lookup + LLM: confidently wrong (all sets)

| Set | ID | Expected | Answered | Evidence | Votes |
|---|---|---|---|---|---|
| core50 | C026 | Pediatric Cardiology | Cardiology | perimembranous VSD; pulmonary hypertension; Surgical closure; echo; my daughter | {'hybrid': 'Cardiology', 'LLM': 'Cardiology'} |
| mediroute | Q082 | Endocrinology | Gastroenterology | ulcer; diabetic | {'hybrid': 'Gastroenterology', 'LLM': None} |
| gretel | G003 | General Medicine | Neurology | headaches; migraines | {'hybrid': 'Neurology', 'LLM': 'Neurology'} |
| gretel | G045 | Neurology | Ophthalmology | visual disturbances; headaches; vision | {'hybrid': 'Ophthalmology', 'LLM': 'Ophthalmology'} |
| gretel | G047 | Endocrinology | Pulmonology | trouble breathing; yeast infections | {'hybrid': 'Pulmonology', 'LLM': 'Pulmonology'} |
| gretel | G050 | General Medicine | Gastroenterology | vomiting; stomach pains; dizziness; arms; back; neck | {'hybrid': 'Gastroenterology', 'LLM': 'Gastroenterology'} |
| gretel | G058 | General Medicine | Pulmonology | coughing a lot; trouble breathing; throat hurts; phlegm in chest; running nose | {'hybrid': 'Pulmonology', 'LLM': 'Pulmonology'} |
| gretel | G095 | General Medicine | Pulmonology | asthma; wheezing; breathing issues; fevers; headaches; tired | {'hybrid': 'Pulmonology', 'LLM': 'Pulmonology'} |
| gretel | G099 | Endocrinology | Dermatology | skin irritations; rashes; skin bruises; skin cuts; crevices | {'hybrid': 'Dermatology', 'LLM': 'Dermatology'} |
| gretel | G102 | Cardiology | Neurology | headache; chest pain; dizziness; trouble concentrating | {'hybrid': 'Neurology', 'LLM': 'Neurology'} |
| gretel | G107 | Endocrinology | Dermatology | rashes; skin irritations; skin bruises; skin cuts; crevices | {'hybrid': 'Dermatology', 'LLM': 'Dermatology'} |
| gretel | G110 | Gastroenterology | ENT | sore throat; scratchy voice; bad breath | {'hybrid': 'ENT', 'LLM': 'ENT'} |
| gretel | G112 | General Medicine | Dermatology | rash; vomiting; itchy; body; joints | {'hybrid': 'Dermatology', 'LLM': 'Dermatology'} |
| gretel | G113 | Neurology | Gastroenterology | headaches; digestive issues; acid reflux; indigestion; sore neck; depression | {'hybrid': 'Gastroenterology', 'LLM': 'Gastroenterology'} |
| gretel | G139 | Urology | Gastroenterology | lower abdomen pain; low body temperature | {'hybrid': 'Gastroenterology', 'LLM': 'Gastroenterology'} |
| gretel | G182 | Cardiology | Neurology | headaches; dizziness | {'hybrid': 'Neurology', 'LLM': 'Neurology'} |
| gretel | G185 | Pulmonology | Cardiology | trouble breathing; chest hurts; heart racing; coughing up dark mucus; sweating a lot; full | {'hybrid': 'Cardiology', 'LLM': 'Cardiology'} |
