# Step 2 evaluation 20261112_095554_step2_judged

Mode: oracle · judged-only (condensed lists) · queries: 45 · git a0f806b (dirty) · hospitals.csv ac2885bbad4c0b1b · grades 0bd01e7fe09cde93

Relevant = grade ≥ 2. Mean [95% bootstrap CI]; queries with no relevant hospital are left out of P / R / NDCG / Hit. p = paired permutation test of NDCG@5 against Ours.

## Overall

| System | NDCG@5 | NDCG@3 | P@3 | P@5 | R@3 | R@5 | Hit@3 | Capable@3 | Bad@3 | OffArea@3 | MaxP@5 | p (NDCG@5) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Ours: filter + FAISS + rerank | 0.729 [0.63, 0.82] | 0.741 [0.65, 0.84] | 0.659 | 0.530 | 0.492 | 0.578 | 0.907 | 0.867 | 0.089 | 0.000 | 0.730 | – |
| B0 random among eligible | 0.682 [0.59, 0.77] | 0.692 [0.60, 0.78] | 0.619 | 0.491 | 0.479 | 0.558 | 0.906 | 0.866 | 0.110 | 0.000 | 0.730 | 0.004 |
| B2 filter, alphabetical | 0.685 [0.59, 0.78] | 0.686 [0.58, 0.78] | 0.612 | 0.493 | 0.465 | 0.554 | 0.884 | 0.844 | 0.111 | 0.000 | 0.730 | 0.043 |
| B3 filter + rule bonuses | 0.736 [0.64, 0.83] | 0.750 [0.65, 0.84] | 0.659 | 0.526 | 0.489 | 0.575 | 0.907 | 0.867 | 0.089 | 0.000 | 0.730 | 0.592 |
| B4 filter + FAISS, no rerank | 0.704 [0.61, 0.79] | 0.715 [0.62, 0.81] | 0.628 | 0.512 | 0.480 | 0.569 | 0.907 | 0.867 | 0.111 | 0.000 | 0.730 | 0.008 |
| A1 ours, website-confirmed only | 0.556 [0.45, 0.66] | 0.588 [0.48, 0.69] | 0.543 | 0.414 | 0.361 | 0.400 | 0.767 | 0.733 | 0.000 | 0.000 | 0.730 | 0.000 |
| A2 ours, no procedure match | 0.728 [0.63, 0.82] | 0.733 [0.64, 0.83] | 0.659 | 0.535 | 0.492 | 0.579 | 0.907 | 0.867 | 0.089 | 0.000 | 0.730 | 0.623 |

## NDCG@5 by stratum

| Stratum | ours | B0 | B2 | B3 | B4 | A1 | A2 |
|---|---|---|---|---|---|---|---|
| S1 | 0.720 | 0.693 | 0.723 | 0.722 | 0.699 | 0.470 | 0.720 |
| S2 | 0.843 | 0.791 | 0.767 | 0.848 | 0.805 | 0.714 | 0.840 |
| S3 | 0.802 | 0.707 | 0.689 | 0.815 | 0.777 | 0.634 | 0.815 |
| S4 | 0.885 | 0.842 | 0.885 | 0.885 | 0.885 | 0.682 | 0.885 |
| S5 | 0.230 | 0.219 | 0.198 | 0.247 | 0.186 | 0.140 | 0.208 |

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
