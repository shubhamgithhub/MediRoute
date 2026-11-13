# Step 2 ranking-weight sensitivity 20261113_161100_step2_weights_allgrades

Mode: oracle · all grades · queries: 45 · git 2a078d7 (dirty) · grades 27771131641ff024

Only the reranker's bonus weights change; retrieval, filters and grades are the same as eval_step2.py. p = paired permutation test of NDCG@5 against the current weights. “Top-5 changed” = queries whose top 5 differs from the current weights.

Current weights: website_specialty 0.04, procedure_each 0.04, procedure_max 0.08, verified 0.03, partially_verified 0.015, nabh 0.02, jci 0.02, international_patients 0.02, evidence_max 0.03, bonus_cap 0.2

| Variant | NDCG@5 | NDCG@3 | P@3 | Hit@3 | Capable@3 | Bad@3 | OffArea@3 | p (NDCG@5) | Top-5 changed | Top-1 changed |
|---|---|---|---|---|---|---|---|---|---|---|
| current | 0.701 [0.62, 0.78] | 0.694 [0.60, 0.79] | 0.729 | 0.907 | 0.867 | 0.156 | 0.089 | – | 0 | 0 |
| no bonuses (similarity only) | 0.648 [0.57, 0.73] | 0.629 [0.54, 0.72] | 0.574 | 0.907 | 0.867 | 0.178 | 0.089 | 0.009 | 43 | 21 |
| all bonuses x0.5 | 0.690 [0.61, 0.77] | 0.684 [0.59, 0.77] | 0.682 | 0.930 | 0.889 | 0.156 | 0.089 | 0.382 | 34 | 9 |
| all bonuses x2 | 0.695 [0.62, 0.77] | 0.687 [0.59, 0.78] | 0.729 | 0.907 | 0.867 | 0.156 | 0.089 | 0.570 | 30 | 5 |
| all bonuses x4 | 0.686 [0.61, 0.76] | 0.671 [0.58, 0.76] | 0.705 | 0.930 | 0.889 | 0.178 | 0.089 | 0.313 | 36 | 12 |
| without website-confirmed speciality | 0.674 [0.59, 0.75] | 0.671 [0.58, 0.76] | 0.674 | 0.907 | 0.867 | 0.200 | 0.089 | 0.004 | 21 | 2 |
| without procedure match | 0.694 [0.61, 0.78] | 0.677 [0.59, 0.77] | 0.729 | 0.907 | 0.867 | 0.156 | 0.089 | 0.128 | 11 | 4 |
| without verified details | 0.694 [0.61, 0.78] | 0.692 [0.60, 0.78] | 0.721 | 0.907 | 0.867 | 0.156 | 0.089 | 0.065 | 17 | 3 |
| without NABH | 0.698 [0.62, 0.78] | 0.690 [0.60, 0.78] | 0.721 | 0.907 | 0.867 | 0.156 | 0.089 | 0.206 | 13 | 2 |
| without JCI | 0.711 [0.63, 0.79] | 0.712 [0.62, 0.80] | 0.744 | 0.907 | 0.867 | 0.156 | 0.089 | 0.209 | 28 | 6 |
| without international services | 0.698 [0.61, 0.78] | 0.692 [0.60, 0.78] | 0.721 | 0.907 | 0.867 | 0.156 | 0.089 | 0.507 | 18 | 6 |
| without evidence quality | 0.697 [0.61, 0.78] | 0.696 [0.60, 0.79] | 0.729 | 0.907 | 0.867 | 0.156 | 0.089 | 0.379 | 10 | 3 |
| no area filter (all India) | 0.157 [0.09, 0.23] | 0.155 [0.08, 0.24] | 0.171 | 0.302 | 0.622 | 0.000 | 0.793 | 0.000 | 39 | 35 |
