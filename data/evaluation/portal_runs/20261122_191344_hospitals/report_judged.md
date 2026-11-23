# Portal hospital benchmark — 20261122_191344_hospitals

Mode: judged-only (condensed lists: hospitals without a website-backed grade dropped). 45 queries (data/evaluation/step2_gold.csv). Relevant = website grade ≥ 2 in the patient's area; NDCG gain 2^grade − 1.

Step 1 picked the gold speciality in 42/45 searches (final decisions: agreement 39, judge 6).

| System | NDCG@5 | NDCG@3 | P@3 | P@5 | R@3 | R@5 | Hit@3 | Capable@3 | Bad@3 | OffArea@3 | MaxP@5 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Portal end to end (patient text → Step 1 → Step 2) | 0.809 [0.73, 0.88] | 0.816 [0.74, 0.89] | 0.729 | 0.605 | 0.559 | 0.678 | 0.953 | 0.978 | 0.156 | 0.104 | 0.730 |
| Reference: engine with the gold speciality + procedure (no Step 1) | 0.807 [0.73, 0.88] | 0.798 [0.71, 0.88] | 0.721 | 0.609 | 0.556 | 0.681 | 0.953 | 0.978 | 0.156 | 0.104 | 0.730 |
| Baseline B0: random among eligible (20 seeds) | 0.750 [0.67, 0.82] | 0.734 [0.66, 0.80] | 0.670 | 0.566 | 0.533 | 0.658 | 0.948 | 0.906 | 0.191 | 0.000 | 0.730 |

Paired permutation test of NDCG@5: portal vs reference p = 0.801; portal vs B0 p = 0.002.

## Portal by Step 1 outcome

| Step 1 | Queries | NDCG@5 | P@5 | R@5 | Hit@3 |
|---|---|---|---|---|---|
| Step 1 right | 42 | 0.817 | 0.585 | 0.711 | 0.950 |
| Step 1 wrong / no answer | 3 | 0.706 | 0.867 | 0.230 | 1.000 |

## NDCG@5 by stratum

| Stratum | Portal | Reference | B0 |
|---|---|---|---|
| S1 | 0.897 | 0.898 | 0.869 |
| S2 | 0.870 | 0.881 | 0.813 |
| S3 | 0.852 | 0.825 | 0.707 |
| S4 | 0.952 | 0.952 | 0.909 |
| S5 | 0.305 | 0.302 | 0.282 |

## Searches where Step 1 did not end on the gold speciality

| Query | Gold | Portal | Follow-ups | Portal NDCG@5 |
|---|---|---|---|---|
| S2-02 | Cardiology | Cardiothoracic Surgery | 0 | 0.558 |
| S3-06 | Cardiothoracic Surgery | Organ Transplant | 0 | 0.742 |
| S3-07 | Cardiology | Cardiothoracic Surgery | 0 | 0.820 |

## Notes

- The simulated patient answers follow-up questions with the gold speciality's body area and picks the gold speciality from a shortlist only when it is offered: favourable to the portal.
- Grades are LLM drafts from the hospitals' websites awaiting the 20% human check.
- `–` = no relevant hospital exists for that query, so P/R/NDCG are undefined and left out of the mean.
- Gave up: none. HTTP failures: none.
- Unjudged hospitals in the area in the portal's top 5: none.
