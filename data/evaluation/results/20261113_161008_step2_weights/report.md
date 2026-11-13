# Step 2 ranking-weight sensitivity 20261113_161008_step2_weights

Mode: oracle · judged-only (condensed lists) · queries: 45 · git 2a078d7 (dirty) · grades 27771131641ff024

Only the reranker's bonus weights change; retrieval, filters and grades are the same as eval_step2.py. p = paired permutation test of NDCG@5 against the current weights. “Top-5 changed” = queries whose top 5 differs from the current weights.

Current weights: website_specialty 0.04, procedure_each 0.04, procedure_max 0.08, verified 0.03, partially_verified 0.015, nabh 0.02, jci 0.02, international_patients 0.02, evidence_max 0.03, bonus_cap 0.2

| Variant | NDCG@5 | NDCG@3 | P@3 | Hit@3 | Capable@3 | Bad@3 | OffArea@3 | p (NDCG@5) | Top-5 changed | Top-1 changed |
|---|---|---|---|---|---|---|---|---|---|---|
| current | 0.807 [0.73, 0.88] | 0.798 [0.71, 0.88] | 0.721 | 0.953 | 0.933 | 0.156 | 0.052 | – | 0 | 0 |
| no bonuses (similarity only) | 0.776 [0.70, 0.85] | 0.768 [0.68, 0.85] | 0.682 | 0.953 | 0.933 | 0.178 | 0.059 | 0.021 | 30 | 14 |
| all bonuses x0.5 | 0.796 [0.72, 0.87] | 0.792 [0.71, 0.87] | 0.705 | 0.953 | 0.933 | 0.156 | 0.059 | 0.150 | 20 | 5 |
| all bonuses x2 | 0.812 [0.73, 0.88] | 0.818 [0.74, 0.89] | 0.736 | 0.953 | 0.933 | 0.156 | 0.052 | 0.717 | 21 | 7 |
| all bonuses x4 | 0.821 [0.74, 0.89] | 0.818 [0.74, 0.89] | 0.736 | 0.953 | 0.933 | 0.156 | 0.052 | 0.295 | 25 | 10 |
| without website-confirmed speciality | 0.795 [0.72, 0.86] | 0.785 [0.70, 0.86] | 0.705 | 0.953 | 0.933 | 0.178 | 0.052 | 0.102 | 13 | 4 |
| without procedure match | 0.802 [0.72, 0.88] | 0.793 [0.71, 0.87] | 0.721 | 0.953 | 0.933 | 0.156 | 0.052 | 0.257 | 7 | 4 |
| without verified details | 0.808 [0.73, 0.88] | 0.800 [0.72, 0.88] | 0.721 | 0.953 | 0.933 | 0.156 | 0.052 | 0.837 | 12 | 2 |
| without NABH | 0.812 [0.73, 0.88] | 0.800 [0.72, 0.88] | 0.721 | 0.953 | 0.933 | 0.156 | 0.052 | 0.249 | 8 | 2 |
| without JCI | 0.808 [0.73, 0.88] | 0.805 [0.72, 0.88] | 0.721 | 0.953 | 0.933 | 0.156 | 0.052 | 0.905 | 16 | 1 |
| without international services | 0.803 [0.72, 0.87] | 0.799 [0.72, 0.88] | 0.721 | 0.953 | 0.933 | 0.156 | 0.052 | 0.500 | 12 | 4 |
| without evidence quality | 0.801 [0.72, 0.87] | 0.798 [0.71, 0.88] | 0.721 | 0.953 | 0.933 | 0.156 | 0.052 | 0.498 | 5 | 2 |
| no area filter (all India) | 0.307 [0.21, 0.41] | 0.318 [0.22, 0.42] | 0.318 | 0.558 | 0.800 | 0.022 | 0.356 | 0.000 | 35 | 26 |
