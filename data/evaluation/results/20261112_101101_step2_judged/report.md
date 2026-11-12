# Step 2 evaluation 20261112_101101_step2_judged

Mode: oracle · judged-only (condensed lists) · queries: 45 · git a0f806b (dirty) · hospitals.csv 0bdec9088b086ecc · grades 0bd01e7fe09cde93

Relevant = grade ≥ 2. Mean [95% bootstrap CI]; queries with no relevant hospital are left out of P / R / NDCG / Hit. p = paired permutation test of NDCG@5 against Ours.

## Overall

| System | NDCG@5 | NDCG@3 | P@3 | P@5 | R@3 | R@5 | Hit@3 | Capable@3 | Bad@3 | OffArea@3 | MaxP@5 | p (NDCG@5) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Ours: filter + FAISS + rerank | 0.807 [0.73, 0.88] | 0.798 [0.71, 0.88] | 0.721 | 0.609 | 0.556 | 0.681 | 0.953 | 0.933 | 0.156 | 0.052 | 0.730 | – |
| B0 random among eligible | 0.750 [0.67, 0.82] | 0.734 [0.66, 0.80] | 0.670 | 0.566 | 0.533 | 0.658 | 0.948 | 0.906 | 0.191 | 0.000 | 0.730 | 0.001 |
| B3 filter + rule bonuses | 0.831 [0.75, 0.90] | 0.824 [0.75, 0.90] | 0.729 | 0.623 | 0.550 | 0.686 | 0.953 | 0.911 | 0.156 | 0.000 | 0.730 | 0.173 |
| A2 ours, no procedure match | 0.802 [0.72, 0.88] | 0.793 [0.71, 0.87] | 0.721 | 0.609 | 0.556 | 0.681 | 0.953 | 0.911 | 0.156 | 0.000 | 0.730 | 0.257 |

## NDCG@5 by stratum

| Stratum | ours | B0 | B3 | A2 |
|---|---|---|---|---|
| S1 | 0.898 | 0.869 | 0.910 | 0.898 |
| S2 | 0.881 | 0.813 | 0.884 | 0.874 |
| S3 | 0.825 | 0.707 | 0.884 | 0.816 |
| S4 | 0.952 | 0.909 | 0.952 | 0.952 |
| S5 | 0.302 | 0.282 | 0.373 | 0.289 |

## Warnings

- S1-01: 7 hospitals in the area have no grade (run `pool`)
- S1-02: 6 hospitals in the area have no grade (run `pool`)
- S1-03: 10 hospitals in the area have no grade (run `pool`)
- S1-04: 11 hospitals in the area have no grade (run `pool`)
- S1-05: 3 hospitals in the area have no grade (run `pool`)
- S1-06: 4 hospitals in the area have no grade (run `pool`)
- S1-07: 6 hospitals in the area have no grade (run `pool`)
- S1-08: 10 hospitals in the area have no grade (run `pool`)
- S1-09: 11 hospitals in the area have no grade (run `pool`)
- S1-10: 7 hospitals in the area have no grade (run `pool`)
- S2-01: 11 hospitals in the area have no grade (run `pool`)
- S2-02: 6 hospitals in the area have no grade (run `pool`)
- S2-03: 11 hospitals in the area have no grade (run `pool`)
- S2-04: 10 hospitals in the area have no grade (run `pool`)
- S2-05: 3 hospitals in the area have no grade (run `pool`)
- S2-06: 7 hospitals in the area have no grade (run `pool`)
- S2-07: 10 hospitals in the area have no grade (run `pool`)
- S2-08: 6 hospitals in the area have no grade (run `pool`)
- S2-09: 6 hospitals in the area have no grade (run `pool`)
- S2-10: 10 hospitals in the area have no grade (run `pool`)
- S2-11: 6 hospitals in the area have no grade (run `pool`)
- S2-12: 7 hospitals in the area have no grade (run `pool`)
- S3-01: 10 hospitals in the area have no grade (run `pool`)
- S3-02: 11 hospitals in the area have no grade (run `pool`)
- S3-03: 7 hospitals in the area have no grade (run `pool`)
- S3-04: 12 hospitals in the area have no grade (run `pool`)
- S4-01: 1 hospitals in the area have no grade (run `pool`)
- S4-02: 2 hospitals in the area have no grade (run `pool`)
- S4-03: 3 hospitals in the area have no grade (run `pool`)
- S4-04: 2 hospitals in the area have no grade (run `pool`)
- S4-07: 1 hospitals in the area have no grade (run `pool`)
- S4-08: 1 hospitals in the area have no grade (run `pool`)
- S5-01: 4 hospitals in the area have no grade (run `pool`)
- S5-02: 6 hospitals in the area have no grade (run `pool`)
- S5-03: 1 hospitals in the area have no grade (run `pool`)
- S5-05: 3 hospitals in the area have no grade (run `pool`)
- S5-06: 10 hospitals in the area have no grade (run `pool`)
