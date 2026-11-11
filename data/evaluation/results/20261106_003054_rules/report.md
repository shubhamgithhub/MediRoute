# Step 1 evaluation: 20261106_003054_rules

Model `None` · prompt `specialty_v1` · routes rules

## step1_gold_mediroute

| Route | n | Top-1 | Acceptable | Top-3 | Macro-F1 | Unclear | Failed | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|---|
| rules | 84 | 83.3% | 88.1% | 88.1% | 0.880 | 9.5% | 0 | 0 | 0 |

Top-1 accuracy by case type:

| Case type | rules |
|---|---|
| clear (n=14) | 100% |
| diagnosis (n=22) | 91% |
| lay (n=31) | 74% |
| misspelled (n=2) | 0% |
| multi (n=3) | 33% |
| report (n=7) | 100% |
| vague (n=5) | 100% |

Most common errors, rules:

- Cardiology → Unclear (2)
- Orthopaedics → Unclear (2)
- Neurology → Unclear (1)
- Gastroenterology → Unclear (1)
- Paediatrics → Unclear (1)
- Pulmonology → Unclear (1)
- Emergency Medicine → Gastroenterology (1)
- Endocrinology → Gastroenterology (1)

## step1_gold_gretel

| Route | n | Top-1 | Acceptable | Top-3 | Macro-F1 | Unclear | Failed | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|---|
| rules | 212 | 29.7% | 45.3% | 50.0% | 0.321 | 17.0% | 0 | 2 | 4 |

Top-1 accuracy by case type:

| Case type | rules |
|---|---|
| gretel (n=212) | 30% |

Most common errors, rules:

- General Medicine → Neurology (15)
- Orthopaedics → Unclear (10)
- Pulmonology → General Medicine (9)
- Cardiology → Neurology (7)
- General Medicine → Unclear (6)
- General Medicine → Ophthalmology (6)
- Urology → Unclear (5)
- Pulmonology → Cardiology (4)
