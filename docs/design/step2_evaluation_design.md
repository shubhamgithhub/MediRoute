# Step 2 evaluation: Precision@K, Recall@K and NDCG@K against baselines

**Date:** 2026-11-11 · **Branch:** `pravin-data-unify` · **Tracker rows:** 20 (hospital-relevance
labels), 21 (baselines), 23 (Step 2 evaluation) · **TA feedback:** "graded hospital-relevance
labels", "keyword search, rule-based mapping and specialty filtering vs our approach",
"Precision@K, Recall@K and NDCG@K".

## Contents

1. [Question](#1-question)
2. [Why the data shapes the design](#2-why-the-data-shapes-the-design)
3. [Query set](#3-query-set)
4. [What is graded](#4-what-is-graded)
5. [Grading rubric and process](#5-grading-rubric-and-process)
6. [Systems compared](#6-systems-compared)
7. [Metrics](#7-metrics)
8. [Files and how to run](#8-files-and-how-to-run)
9. [Reproducibility](#9-reproducibility)
10. [Plan](#10-plan)
11. [Limits we will state in the report](#11-limits-we-will-state-in-the-report)

---

## 1. Question

> Given the right speciality, procedure and location, does Step 2 put the hospitals that can
> treat the patient at the top, and does it do better than simpler methods?

- **Oracle mode (first):** each query carries the gold speciality and procedure, so only Step 2
  is measured.
- **End-to-end mode (after the Step 1 evaluation):** Step 1's output feeds Step 2, to show how
  much Step 1 errors cost. Same queries, same grades.

Building this harness comes **before** AHP-TOPSIS or any weight change, so each change can be
measured against the same baselines (the TA's "measured incremental value").

## 2. Why the data shapes the design

Measured on `data/processed/hospitals.csv` (201 hospitals, 55 search areas, 2026-11-11):

- After the speciality and location filters, **89% of speciality × area pairs leave ≤ 5
  hospitals** (median 1–2). Only Delhi NCR (16), Mumbai (17), Hyderabad (12), Chennai (13),
  Kolkata (11) and Bengaluru (10) leave 8 or more, and only for the big specialities.
- In a small city every filtered method returns the same few hospitals, so P@5 and R@5 cannot
  separate them. Differences show in **big areas**, **state / no-preference** searches and
  **procedure-specific** needs (TAVR: 17 hospitals list it; kidney transplant: 39; BMT: 11).
- **Procedures come only from the team 150 sheet** (150 of 201 hospitals, not verified). IVF,
  cataract and bariatric surgery are listed by no hospital.

## 3. Query set

About 45 queries in `data/evaluation/step2_gold.csv`, in five strata. Results are reported per
stratum as well as overall; S4 is reported separately so small cities don't dilute the averages.

| Stratum | What | Example | Count |
|---|---|---|---|
| S1 | Big area + speciality only | Neurology, Hyderabad | 10 |
| S2 | Big area + procedure | TAVR, Mumbai; kidney transplant, Chennai; BMT, Delhi NCR | 12 |
| S3 | State or no preference + procedure | Liver transplant, anywhere; knee replacement, Maharashtra | 8 |
| S4 | Small city | Cardiology, Pune | 8 |
| S5 | Edge cases | Dermatology, Kochi; IVF (no hospital lists it); vague lay wording | 7 |

Columns: `query_id, patient_text, specialty, procedure, diagnoses, preferred_city,
preferred_state, stratum, notes`. One need per query: a speciality and at most one procedure.
Wording reuses `step1_gold_core50.csv` where possible, with a location added. Specialities use
the 26 names in `data/medical_taxonomy/specialties.csv`; cities use `data/reference/cities.csv`.

## 4. What is graded

Relevance depends on two things, and only one needs a person:

- **Location** is mechanical: a hospital outside the area the patient chose has relevance 0. The
  script applies this using `data/reference/cities.csv` (Delhi NCR = New Delhi + Gurugram + Noida).
- **Capability** needs judgement: can this hospital handle this speciality and procedure?

So graders grade **(hospital, need) pairs**, where a need is a speciality plus an optional
procedure. A pair is graded once and reused by every query with that need: "Apollo Chennai ×
Nephrology + kidney transplant" is graded once.

**Size (measured on a 6-query dry run, 2026-11-11):** an area query needs 8–17 pairs; a
no-preference procedure query needs about 60 (every system's top 10 plus the 39 hospitals that
mention "kidney transplant"). For 45 queries that is about **700–800 pairs**, most of them from
S3. They involve at most 201 hospitals, so the work is **one website visit per hospital, grading
all of its needs at once**, not one visit per pair. To keep S3 manageable, half of its queries
are state-level (≤ 40 hospitals, judged completely) and half are no-preference (pooled).

Which hospitals are graded for a query (the **judged set**):

- **Area has ≤ 40 hospitals** (every city or area query, most state queries): grade *all* of them,
  whatever their listed specialities. The judgements are complete, so Recall@K is exact.
- **Larger pools** (no preference, big states): grade the union of every system's top 10, plus every
  hospital whose data mentions the procedure (TREC-style pooling). Recall is then measured against
  the judged set, and the report says so.

## 5. Grading rubric and process

| Grade | Meaning |
|---|---|
| 3 | The hospital's own website (or NABH / JCI listing) confirms the speciality **and** the procedure or condition |
| 2 | Speciality confirmed; procedure not confirmed (or the need has no procedure) |
| 1 | Related speciality only, or the speciality appears only in the team sheet and cannot be confirmed |
| 0 | Cannot treat this need |

Rules:

- **Grade from the hospital's website, not from our CSV.** Our procedure data is the unverified team
  sheet and our speciality data is what the system ranks on; grading from it would score the system
  against its own input. Every grade of 2 or 3 records an `evidence_url`.
- Graders never see a system's ranking or score.
- **Process (agreed 2026-11-11):** Claude drafts every grade with its evidence URL. Anand and Ravi
  blind-regrade a random 20% of pairs plus every grade-3 pair. We report weighted Cohen's kappa
  (target ≥ 0.6) and resolve disagreements; the resolved grade is the one used.

Grades file `data/evaluation/step2_capability_grades.csv`: `hospital_id, hospital_name, specialty,
procedure, grade, evidence_url, evidence_note, grader, graded_on, confidence, review_grade,
reviewer`. When `review_grade` is filled, it overrides `grade`.

## 6. Systems compared

Every system has the same interface, `rank(query) → [hospital_id, …]`, and uses the engine's own
components, so the comparison is about the method, not the code.

| ID | System | What it shows |
|---|---|---|
| B0 | Random order among the eligible hospitals (speciality + location filter), mean of 20 seeds | Floor |
| B1 | TF-IDF keyword search over the hospital text with the patient's wording, no filters (`keyword_retriever.py`) | Value of the structured filters |
| B2 | Speciality + location filter, alphabetical order | Value of any ranking beyond the filter |
| B3 | Filter + rule bonuses only (website-confirmed speciality, procedure match, verification, NABH, JCI, international, evidence) | Rule-based ranking |
| B4 | Filter + FAISS semantic search, no rerank | Value of the rerank bonuses |
| **Ours** | `HospitalRecommendationEngine.recommend` (filter + FAISS + rerank), `top_k=5` as in production | |
| A1 | Ours, but only website-confirmed specialities are eligible | Do team-sheet hospitals help or hurt? |
| A2 | Ours, rerank without procedure matching | Value of procedure matching |

## 7. Metrics

For a query, *rel(h)* = capability grade if *h* is in the patient's area, else 0. A hospital is
**relevant** when *rel ≥ 2*. K = 3 and 5.

| Metric | Definition | Role |
|---|---|---|
| **NDCG@K** | DCG@K / ideal DCG@K, gain 2^rel − 1, discount log2(rank + 1); the ideal ranking uses every judged hospital for the query | Headline (NDCG@5) |
| P@K | relevant in top K / K (fewer than K results still divide by K) | What the patient sees |
| R@K | relevant in top K / relevant in the judged set | Missed good options |
| Hit@3 | at least one relevant hospital in the top 3 | Patient gets a usable answer |
| Bad@3 | a top-3 hospital with capability 0 (cannot treat) | Safety |
| Max P@K | min(K, number relevant) / K | Shows when a low P@K is thin data, not bad ranking |

- Queries with no relevant hospital are left out of P, R and NDCG averages; for them we report
  Bad@3 and whether the system returned anything.
- An unjudged hospital in a top K counts as 0 and the run lists it, so it can be graded.
- **Uncertainty:** bootstrap 95% CI over queries (2,000 resamples) for each mean; paired
  sign-flip permutation test (10,000) of Ours vs each baseline on NDCG@5.

## 8. Files and how to run

| File | What |
|---|---|
| `src/mediroute/evaluation/ranking_metrics.py` | P@K, R@K, NDCG@K, Hit, Bad, bootstrap, permutation test (unit-tested in `tests/evaluation/`) |
| `scripts/eval_step2.py` | Runs every system on every query, pools, computes metrics |
| `data/evaluation/step2_gold.csv` | Queries |
| `data/evaluation/step2_capability_grades.csv` | Grades |
| `data/evaluation/results/<run_id>_step2/` | `rankings.csv`, `per_query.csv`, `metrics.json`, `report.md` |

```powershell
$env:PYTHONPATH = "src"
# 1. list the (hospital, need) pairs that still need a grade -> data/evaluation/step2_to_grade.csv
.venv\Scripts\python.exe scripts/eval_step2.py pool
# 2. after grading: metrics for every system
.venv\Scripts\python.exe scripts/eval_step2.py run
```

## 9. Reproducibility

Each run records the git commit (and whether the tree was dirty), a SHA-256 of `hospitals.csv`
and `hospital_metadata.json`, the embedding model and the random seeds. Grades are keyed by
`hospital_id`; the script also checks the hospital name, so a data rebuild that renumbers
hospitals stops the run instead of silently shifting labels. **Grading starts only after the data
reorganisation on `pravin-data-unify` is committed.**

## 10. Plan

| When | What | Who |
|---|---|---|
| 11–12 Nov | Metrics module, script, all baselines, tested on dummy grades | Pravin + Claude |
| 12 Nov | Data frozen (data reorganisation committed) | Pravin |
| 12–13 Nov | Draft 45 queries; team review | Claude drafts, Anand / Ravi review |
| 13–16 Nov | Claude drafts grades with evidence URLs | Claude |
| 16–17 Nov | Blind regrade of 20% + all grade-3s, kappa, resolve | Anand, Ravi |
| 18 Nov | First results; add to the tracker and experiments log | All |
| After | End-to-end mode; AHP-TOPSIS and weight experiments measured on this harness | |

## 11. Limits we will state in the report

- About 45 queries: differences under about 0.05 NDCG may not be significant; the CIs show it.
- Most cities have so few hospitals that ranking barely matters there; S4 shows this openly.
- Recall for pooled queries is relative to the judged set.
- Grades are drafted by an LLM and checked by the team on a sample; agreement (kappa) is reported.
  A doctor's review of the rubric would make them stronger.
- Capability grades say nothing about outcomes, waiting times or cost.
