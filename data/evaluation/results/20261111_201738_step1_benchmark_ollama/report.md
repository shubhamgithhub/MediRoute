# Step 1 benchmark: 20261111_201738_step1_benchmark_ollama

LLM `ollama:llama3.2` · gold sets core50 · 50 queries · started 2026-11-11T20:17:38

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
| 1 Keyword search (TF-IDF) | 82% (69%–90%) | 90% | 0.77 | 0.86 | 0.67 | 0.70 | 0.67 | 18% | — |
| 2 Semantic search (embeddings) | 82% (69%–90%) | 98% | 0.81 | 0.90 | 0.61 | 0.62 | 0.59 | 18% | — |
| 3 LLM only | 82% (69%–90%) | 90% | 0.77 | 0.85 | 0.83 | 0.78 | 0.79 | 10% | — |
| Before: current pipeline (3 voters) | 80% (67%–89%) | 90% | 0.80 | 0.86 | 0.79 | 0.77 | 0.77 | 4% | 16% |

Before: current pipeline (3 voters) against each method, same queries (McNemar exact test on accuracy):

| Compared with | Only it right | Only the other right | p-value |
|---|---|---|---|
| 1 Keyword search (TF-IDF) | 3 | 4 | 1.0 |
| 2 Semantic search (embeddings) | 4 | 5 | 1.0 |
| 3 LLM only | 3 | 4 | 1.0 |
| B0 most common speciality (floor) | 35 | 1 | 0.0 |
| B1 keyword rules (specialties.csv) | 7 | 3 | 0.3438 |
| A1 keyword search on LLM evidence | 2 | 2 | 1.0 |
| A2 semantic search on LLM evidence | 1 | 2 | 1.0 |
| A3 3-voter pipeline without LLM | 10 | 1 | 0.0117 |

Before: current pipeline (3 voters): decisions {'majority': 42, 'clarification_required': 8}, clarification rate 16%, acceptable speciality among the candidates when it asked: 38%, vague cases asked 4/5, clear cases answered correctly 39/45

A3 3-voter pipeline without LLM: decisions {'majority': 33, 'clarification_required': 17}, clarification rate 34%, acceptable speciality among the candidates when it asked: 24%, vague cases asked 5/5, clear cases answered correctly 31/45

Evidence extraction by the LLM (shared by the pipelines): critical-detail recall 71% (omission 29%); by kind {'body_part': '28/45 (62%)', 'condition': '32/47 (68%)', 'procedure': '28/32 (88%)'}

Emergency rules: caught 3/3 emergencies, 0 false alarms in 47 non-emergencies

## Appendix: other baselines and ablations

### core50

| Method | Accuracy (95% CI) | Recall@3 | NDCG@3 | MRR@3 | Macro precision | Macro recall | Macro-F1 | Confidently wrong | Asks |
|---|---|---|---|---|---|---|---|---|---|
| B0 most common speciality (floor) | 12% (6%–24%) | 12% | 0.10 | 0.12 | 0.00 | 0.04 | 0.01 | 88% | — |
| B1 keyword rules (specialties.csv) | 72% (58%–82%) | 76% | 0.66 | 0.74 | 0.78 | 0.67 | 0.69 | 4% | — |
| A1 keyword search on LLM evidence | 80% (67%–89%) | 88% | 0.76 | 0.83 | 0.77 | 0.77 | 0.75 | 12% | — |
| A2 semantic search on LLM evidence | 82% (69%–90%) | 86% | 0.76 | 0.84 | 0.78 | 0.78 | 0.75 | 10% | — |
| A3 3-voter pipeline without LLM | 62% (48%–74%) | 74% | 0.64 | 0.70 | 0.72 | 0.61 | 0.65 | 4% | 34% |

## Before: current pipeline (3 voters): confidently wrong (all sets)

| Set | ID | Expected | Answered | Evidence | Votes |
|---|---|---|---|---|---|
| core50 | C007 | Plastic & Reconstructive Surgery | Orthopaedics | burn contracture of the neck; reconstruction surgery; accident; head | {'V1': 'Orthopaedics', 'V2': 'Orthopaedics', 'V3': 'Plastic & Reconstructive Surgery'} |
| core50 | C026 | Pediatric Cardiology | Cardiology | perimembranous VSD; pulmonary hypertension; Surgical closure | {'V1': 'Cardiology', 'V2': 'Obstetrics & Gynaecology', 'V3': 'Cardiology'} |
