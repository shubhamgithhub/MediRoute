# Portal hospital benchmark — 20261122_191344_hospitals

Mode: all grades (draft grades included; unjudged hospitals count as 0). 45 queries (data/evaluation/step2_gold.csv). Relevant = website grade ≥ 2 in the patient's area; NDCG gain 2^grade − 1.

Step 1 picked the gold speciality in 42/45 searches (final decisions: agreement 39, judge 6).

| System | NDCG@5 | NDCG@3 | P@3 | P@5 | R@3 | R@5 | Hit@3 | Capable@3 | Bad@3 | OffArea@3 | MaxP@5 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Portal end to end (patient text → Step 1 → Step 2) | 0.698 [0.62, 0.77] | 0.681 [0.59, 0.77] | 0.705 | 0.651 | 0.375 | 0.494 | 0.907 | 0.911 | 0.178 | 0.089 | 0.847 |
| Reference: engine with the gold speciality + procedure (no Step 1) | 0.698 [0.61, 0.78] | 0.692 [0.60, 0.78] | 0.721 | 0.642 | 0.383 | 0.487 | 0.907 | 0.911 | 0.178 | 0.089 | 0.847 |
| Baseline B0: random among eligible (20 seeds) | 0.597 [0.52, 0.68] | 0.568 [0.49, 0.65] | 0.596 | 0.545 | 0.341 | 0.458 | 0.894 | 0.854 | 0.279 | 0.000 | 0.847 |

Paired permutation test of NDCG@5: portal vs reference p = 0.955; portal vs B0 p = 0.002.

## Portal by Step 1 outcome

| Step 1 | Queries | NDCG@5 | P@5 | R@5 | Hit@3 |
|---|---|---|---|---|---|
| Step 1 right | 42 | 0.701 | 0.635 | 0.518 | 0.900 |
| Step 1 wrong / no answer | 3 | 0.666 | 0.867 | 0.174 | 1.000 |

## NDCG@5 by stratum

| Stratum | Portal | Reference | B0 |
|---|---|---|---|
| S1 | 0.729 | 0.767 | 0.697 |
| S2 | 0.687 | 0.664 | 0.561 |
| S3 | 0.726 | 0.702 | 0.480 |
| S4 | 0.956 | 0.956 | 0.911 |
| S5 | 0.288 | 0.293 | 0.237 |

## Searches where Step 1 did not end on the gold speciality

| Query | Gold | Portal | Follow-ups | Portal NDCG@5 |
|---|---|---|---|---|
| S2-02 | Cardiology | Cardiothoracic Surgery | 0 | 0.608 |
| S3-06 | Cardiothoracic Surgery | Organ Transplant | 0 | 0.671 |
| S3-07 | Cardiology | Cardiothoracic Surgery | 0 | 0.719 |

## Notes

- The simulated patient answers follow-up questions with the gold speciality's body area and picks the gold speciality from a shortlist only when it is offered: favourable to the portal.
- Grades are LLM drafts from the hospitals' websites awaiting the 20% human check.
- `–` = no relevant hospital exists for that query, so P/R/NDCG are undefined and left out of the mean.
- Gave up: none. HTTP failures: none.
- Unjudged hospitals in the area in the portal's top 5: none.
