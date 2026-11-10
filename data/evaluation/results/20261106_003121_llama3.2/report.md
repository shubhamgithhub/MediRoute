# Step 1 evaluation: 20261106_003121_llama3.2

Model `llama3.2` · prompt `specialty_v1` · routes rules, llm, hybrid

## step1_gold_mediroute

| Route | n | Top-1 | Acceptable | Top-3 | Macro-F1 | Unclear | Failed | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|---|
| rules | 3 | 66.7% | 66.7% | 66.7% | 0.800 | 33.3% | 0 | 3 | 5 |
| llm | 3 | 100.0% | 100.0% | 100.0% | 1.000 | 0.0% | 0 | 16294 | 45179 |
| hybrid | 3 | 100.0% | 100.0% | 100.0% | 1.000 | 0.0% | 0 | 16295 | 45184 |

Hybrid top-1 accuracy by confidence:

- high: 100.0% of 2
- low: 100.0% of 1

Top-1 accuracy by case type:

| Case type | rules | llm | hybrid |
|---|---|---|---|
| diagnosis (n=1) | 100% | 100% | 100% |
| lay (n=1) | 0% | 100% | 100% |
| multi (n=1) | 100% | 100% | 100% |

Most common errors, rules:

- Cardiology → Unclear (1)

Most common errors, llm:

- none

Most common errors, hybrid:

- none

## step1_gold_gretel

| Route | n | Top-1 | Acceptable | Top-3 | Macro-F1 | Unclear | Failed | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|---|
| rules | 3 | 33.3% | 33.3% | 33.3% | 0.333 | 33.3% | 0 | 4 | 5 |
| llm | 3 | 66.7% | 66.7% | 66.7% | 0.500 | 0.0% | 0 | 18083 | 23083 |
| hybrid | 3 | 66.7% | 66.7% | 66.7% | 0.500 | 0.0% | 0 | 18087 | 23086 |

Hybrid top-1 accuracy by confidence:

- high: 100.0% of 1
- low: 0.0% of 1
- medium: 100.0% of 1

Top-1 accuracy by case type:

| Case type | rules | llm | hybrid |
|---|---|---|---|
| drug reaction (n=1) | 0% | 0% | 0% |
| peptic ulcer disease (n=2) | 50% | 100% | 100% |

Most common errors, rules:

- Gastroenterology → ENT (1)
- General Medicine → Unclear (1)

Most common errors, llm:

- General Medicine → Neurology (1)

Most common errors, hybrid:

- General Medicine → Neurology (1)
