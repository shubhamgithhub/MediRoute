# Step 1 benchmark: 20261111_201738_step1_benchmark_ollama + method 4 (replay)

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
| 4 MediRoute: hybrid lookup + LLM | 64% (50%–76%) | 92% | 0.82 | 0.87 | 0.84 | 0.69 | 0.74 | 0% | 36% |
| 4b same, but asks when the LLM abstains | 64% (50%–76%) | 92% | 0.82 | 0.87 | 0.84 | 0.69 | 0.74 | 0% | 36% |
| Before: current pipeline (3 voters) | 80% (67%–89%) | 90% | 0.80 | 0.86 | 0.79 | 0.77 | 0.77 | 4% | 16% |

4 MediRoute: hybrid lookup + LLM against each method, same queries (McNemar exact test on accuracy):

| Compared with | Only it right | Only the other right | p-value |
|---|---|---|---|
| 1 Keyword search (TF-IDF) | 3 | 12 | 0.0352 |
| 2 Semantic search (embeddings) | 4 | 13 | 0.049 |
| 3 LLM only | 0 | 9 | 0.0039 |
| 4b same, but asks when the LLM abstains | 0 | 0 | 1.0 |
| Before: current pipeline (3 voters) | 0 | 8 | 0.0078 |
| B0 most common speciality (floor) | 28 | 2 | 0.0 |
| B1 keyword rules (specialties.csv) | 5 | 9 | 0.424 |
| A1 keyword search on LLM evidence | 2 | 10 | 0.0386 |
| A2 semantic search on LLM evidence | 0 | 9 | 0.0039 |
| A3 3-voter pipeline without LLM | 7 | 6 | 1.0 |
| A4 hybrid lookup voter alone, on LLM evidence | 0 | 10 | 0.002 |

4 MediRoute: hybrid lookup + LLM: decisions {'majority': 32, 'clarification_required': 18}, clarification rate 36%, acceptable speciality among the candidates when it asked: 72%, vague cases asked 4/5, clear cases answered correctly 31/45

4b same, but asks when the LLM abstains: decisions {'majority': 32, 'clarification_required': 18}, clarification rate 36%, acceptable speciality among the candidates when it asked: 72%, vague cases asked 4/5, clear cases answered correctly 31/45

Before: current pipeline (3 voters): decisions {'majority': 42, 'clarification_required': 8}, clarification rate 16%, acceptable speciality among the candidates when it asked: 38%, vague cases asked 4/5, clear cases answered correctly 39/45

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
| A4 hybrid lookup voter alone, on LLM evidence | 84% (72%–92%) | 90% | 0.79 | 0.87 | 0.83 | 0.80 | 0.78 | 8% | — |
