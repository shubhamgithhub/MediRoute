# Step 1: CCSR mapping and scoring fixes (20261111_144211_step1_benchmark_ollama)

Same LLM evidence and LLM votes as the benchmark run; only the lookup voter changes. One change per row. Accuracy counts a clarification question as not correct. The CCSR table is a draft awaiting doctor review.

## core50 (n=50)

| Variant | Accuracy (95% CI) | Recall@3 | NDCG@3 | Macro-F1 | Confidently wrong | Asks |
|---|---|---|---|---|---|---|
| C0 current lookup (our ICD ranges) · lookup alone | 84% (72%–92%) | 88% | 0.79 | 0.81 | 8% | — |
| C0 current lookup (our ICD ranges) · + LLM (agree or ask) | 68% (54%–79%) | 90% | 0.82 | 0.77 | 2% | 30% |
| C1 + CCSR mapping · lookup alone | 84% (72%–92%) | 90% | 0.81 | 0.78 | 8% | — |
| C1 + CCSR mapping · + LLM (agree or ask) | 66% (52%–78%) | 92% | 0.83 | 0.73 | 2% | 32% |
| C2 + symptoms count half · lookup alone | 84% (72%–92%) | 90% | 0.81 | 0.78 | 8% | — |
| C2 + symptoms count half · + LLM (agree or ask) | 66% (52%–78%) | 92% | 0.83 | 0.73 | 2% | 32% |
| C3 + best match per phrase · lookup alone | 86% (74%–93%) | 90% | 0.82 | 0.78 | 6% | — |
| C3 + best match per phrase · + LLM (agree or ask) | 68% (54%–79%) | 92% | 0.84 | 0.73 | 2% | 30% |

Perfect-judge ceiling (+ LLM, tie-break always picks the right voter):

| Variant | Accuracy | Confidently wrong | Disagreements where both voters are wrong |
|---|---|---|---|
| C0 current lookup (our ICD ranges) | 84% | 2% | 2 |
| C1 + CCSR mapping | 86% | 2% | 1 |
| C2 + symptoms count half | 86% | 2% | 1 |
| C3 + best match per phrase | 86% | 2% | 1 |

## mediroute (n=84)

| Variant | Accuracy (95% CI) | Recall@3 | NDCG@3 | Macro-F1 | Confidently wrong | Asks |
|---|---|---|---|---|---|---|
| C0 current lookup (our ICD ranges) · lookup alone | 90% (82%–95%) | 99% | 0.84 | 0.77 | 10% | — |
| C0 current lookup (our ICD ranges) · + LLM (agree or ask) | 67% (56%–76%) | 99% | 0.86 | 0.69 | 1% | 32% |
| C1 + CCSR mapping · lookup alone | 90% (82%–95%) | 99% | 0.85 | 0.76 | 10% | — |
| C1 + CCSR mapping · + LLM (agree or ask) | 66% (55%–75%) | 98% | 0.85 | 0.69 | 1% | 33% |
| C2 + symptoms count half · lookup alone | 90% (82%–95%) | 99% | 0.85 | 0.78 | 10% | — |
| C2 + symptoms count half · + LLM (agree or ask) | 68% (57%–77%) | 98% | 0.86 | 0.70 | 1% | 31% |
| C3 + best match per phrase · lookup alone | 95% (88%–98%) | 99% | 0.87 | 0.83 | 5% | — |
| C3 + best match per phrase · + LLM (agree or ask) | 70% (60%–79%) | 100% | 0.89 | 0.73 | 1% | 29% |

Perfect-judge ceiling (+ LLM, tie-break always picks the right voter):

| Variant | Accuracy | Confidently wrong | Disagreements where both voters are wrong |
|---|---|---|---|
| C0 current lookup (our ICD ranges) | 89% | 1% | 4 |
| C1 + CCSR mapping | 89% | 1% | 4 |
| C2 + symptoms count half | 89% | 1% | 4 |
| C3 + best match per phrase | 92% | 1% | 2 |

## gretel (n=212)

| Variant | Accuracy (95% CI) | Recall@3 | NDCG@3 | Macro-F1 | Confidently wrong | Asks |
|---|---|---|---|---|---|---|
| C0 current lookup (our ICD ranges) · lookup alone | 56% (49%–63%) | 71% | 0.47 | 0.47 | 43% | — |
| C0 current lookup (our ICD ranges) · + LLM (agree or ask) | 34% (28%–41%) | 92% | 0.66 | 0.32 | 7% | 58% |
| C1 + CCSR mapping · lookup alone | 57% (51%–64%) | 74% | 0.48 | 0.47 | 42% | — |
| C1 + CCSR mapping · + LLM (agree or ask) | 36% (30%–43%) | 91% | 0.65 | 0.34 | 8% | 55% |
| C2 + symptoms count half · lookup alone | 57% (51%–64%) | 74% | 0.49 | 0.47 | 42% | — |
| C2 + symptoms count half · + LLM (agree or ask) | 37% (31%–44%) | 92% | 0.66 | 0.34 | 9% | 54% |
| C3 + best match per phrase · lookup alone | 57% (50%–64%) | 75% | 0.49 | 0.47 | 42% | — |
| C3 + best match per phrase · + LLM (agree or ask) | 37% (31%–44%) | 92% | 0.66 | 0.32 | 11% | 52% |

Perfect-judge ceiling (+ LLM, tie-break always picks the right voter):

| Variant | Accuracy | Confidently wrong | Disagreements where both voters are wrong |
|---|---|---|---|
| C0 current lookup (our ICD ranges) | 84% | 7% | 16 |
| C1 + CCSR mapping | 83% | 8% | 17 |
| C2 + symptoms count half | 82% | 9% | 17 |
| C3 + best match per phrase | 82% | 11% | 13 |

## Probe phrases: top lookup specialities per variant

| Phrase | C0 | C1 | C2 | C3 |
|---|---|---|---|---|
| throat pain | Cardiology, ENT, Orthopaedics | ENT, Pulmonology, Emergency Medicine | ENT, Pulmonology, Emergency Medicine | ENT, Pulmonology, Emergency Medicine |
| difficulty in talking | Neurology, Paediatrics, Urology | Neurology, Paediatrics, Urology | Paediatrics, Psychiatry, ENT | Paediatrics, Psychiatry, ENT |
| kidney stone | Urology, Nephrology, Orthopaedics | Urology, Nephrology | Urology, Nephrology | Urology, Nephrology |
| severe pain on one side of back | Orthopaedics, Gastroenterology, Ophthalmology | Orthopaedics, Critical Care, Gastroenterology | Orthopaedics, Critical Care, Gastroenterology | Orthopaedics, Critical Care, Gastroenterology |
| chest pain | Cardiology, Pulmonology, Orthopaedics | Cardiology, ENT, Pulmonology | Cardiology, Pulmonology, ENT | Cardiology, Pulmonology, ENT |
| type 2 diabetes | Endocrinology | Endocrinology | Endocrinology | Endocrinology |
| kidney stone + severe pain on one side of back (Q031) | Orthopaedics, Urology, Nephrology | Urology, Orthopaedics, Nephrology | Urology, Orthopaedics, Nephrology | Urology, Orthopaedics, Nephrology |