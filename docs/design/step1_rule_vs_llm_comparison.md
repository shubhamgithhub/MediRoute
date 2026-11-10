# Step 1: rule route vs LLM route (comparison design)

**Status:** Draft for review · **Owner:** Pravin (with Claude Code) · **Date:** 2026-11-06
**Parent design:** [step1_specialty_routing_design.md](step1_specialty_routing_design.md)

## Contents

1. [Question](#1-question)
2. [The two routes](#2-the-two-routes)
3. [Design comparison](#3-design-comparison)
4. [How we compare them (evaluation design)](#4-how-we-compare-them-evaluation-design)
5. [Decision rule, fixed before the LLM results](#5-decision-rule-fixed-before-the-llm-results)
6. [What the research says](#6-what-the-research-says)
7. [Results](#7-results)
8. [Recommendation and next steps](#8-recommendation-and-next-steps)

---

## 1. Question

Which route should turn a patient's text into a specialty: a **deterministic rule route**, an
**LLM route**, or a combination? We decide on measured results, as the TA asked (baselines,
measurable improvement), not on preference.

## 2. The two routes

Both routes use the same input (patient text) and the same output: one specialty name from the
26-name canonical list in `data/medical_taxonomy/specialties.csv`, ranked alternatives, the
evidence terms, and a reason.

**Route 1: rules (deterministic).**
1. Lower-case the text and strip punctuation.
2. For each specialty, match its keywords from `specialties.csv` as whole words or phrases.
3. Score each specialty: 1 point per matched keyword, plus 0.5 for each extra word in a phrase,
   since longer phrases are more specific.
4. The highest score wins; ties keep the CSV order.
5. No match → `Unclear`.

The evidence is the matched keywords.

**Route 2: LLM (local, open source).**
1. Send a versioned prompt (`prompts/specialty_v1.txt`) to `llama3.2` (3B) on Ollama. It lists all
   26 specialties with a one-line description each, plus the patient text.
2. Ollama's JSON-schema `enum` forces the answer to be one of the 26 names or `Unclear`, so the
   model cannot invent a name.
3. The model returns `specialty`, up to 2 `alternatives` and `evidence_terms` (words from the
   text).
4. The code checks the name again and builds the reason from the evidence terms.

Temperature 0 and a fixed seed, so the same input gives the same answer.

**Option 3: hybrid.** The LLM decides and the rules give a second opinion:
- both agree → **high** confidence
- one appears in the other's top 3 → **medium**
- they disagree → **low**
- LLM down or `Unclear` → use the rules' answer at **low** confidence

Low confidence → ask a clarifying question.

## 3. Design comparison

| Aspect | Rules | LLM | Hybrid |
|--------|-------|-----|--------|
| **How it matches** | Exact keywords. "chest tightness" misses if only "chest pain" is listed | Meaning. Handles paraphrase, lay words, and diagnosis vs symptom | LLM meaning, rules as a check |
| **Same input → same output** | Always | Yes at temperature 0 with a fixed seed on the same model build; can change if the model version changes | As LLM |
| **Explainability** | Exact matched keywords, fully traceable | Evidence terms chosen by the model; usually right, not guaranteed | Both, plus an agreement label |
| **Misspellings** ("chest pian") | Fail, unless we add fuzzy matching | Usually tolerant | Tolerant |
| **Multi-symptom / context** ("panic attacks, cardiac tests normal") | Counts words and can't weigh context; picks Cardiology | Can use context ("tests normal" → Psychiatry) | As LLM |
| **Negation** ("no fever") | Counts "fever" as a match | Understands negation | As LLM |
| **Speed on our laptop (CPU)** | Under 5 ms | About 6–7 s warm, 20–40 s cold load | About LLM + 5 ms |
| **Running cost** | None | None (local); about 2 GB RAM | As LLM |
| **Failure mode** | Silent: wrong or `Unclear`, never crashes | Ollama down or timeout → no answer | Falls back to rules |
| **Maintenance** | Keyword lists grow by hand, and every gap is a new rule | Edit descriptions or prompt; re-run evaluation | Both, but keywords only need to be "good enough" |
| **Bias risk** | Keywords reflect whoever wrote them (see §4 "author bias") | Model's training data, unknown | Mixed |
| **Safety (emergencies)** | Predictable, good for red-flag checks | Not reliable enough alone for safety | Use rules for red flags in any option |
| **Confidence signal** | Keyword score and margin | Self-reported confidence is useless (always 0.9–1.0 in our probe) | Agreement between two independent methods |

Expected trade-off: rules are fast, free and transparent but brittle on how real patients write.
The LLM is better on language but slower and less transparent. The hybrid tries to get the LLM's
accuracy with an honest confidence label and a fallback.

## 4. How we compare them (evaluation design)

**Two gold sets, deliberately different:**

| Set | Rows | Source | What it tests | Weakness |
|-----|------|--------|---------------|----------|
| `step1_gold_mediroute.csv` | 84 | Written by the team for our use case: all 26 specialties; clear, lay, diagnosis, report-style, vague, misspelled and multi-symptom cases | In-domain coverage (transplants, IVF, cancer, cardiac surgery) | **Author bias:** the same person wrote the queries and the rule keywords, so rules look better than they are |
| `step1_gold_gretel.csv` | 212 | [gretelai/symptom_to_diagnosis](https://huggingface.co/datasets/gretelai/symptom_to_diagnosis) test split (Apache-2.0): patient-style symptom descriptions for 22 diagnoses, mapped by us to a specialty plus acceptable alternatives | **Independent wording**, written by someone else | Mostly primary-care conditions (malaria, cold, UTI); few medical-travel cases. Our diagnosis → specialty mapping still needs review |

Using both is the point: the first shows coverage of our domain, the second shows how a route
copes with wording it was not written for.

**Metrics** (computed by `scripts/eval_step1.py`):
- **Top-1 accuracy:** first answer = expected specialty. Main metric.
- **Acceptable accuracy:** first answer is the expected specialty or a listed acceptable
  alternative (e.g. Nephrology for a dialysis patient seeking a transplant).
- **Top-3 accuracy:** expected specialty is among the first 3 suggestions. This matters because
  Step 2 can search the alternatives.
- **Macro-F1:** the average over specialties, so small specialties count as much as big ones.
- **Unclear rate:** how often the route declines to answer.
- **Latency:** p50 and p95.
- **Hybrid only:** accuracy within each confidence level. High should be almost always right;
  otherwise the label is not useful.

**Fairness rules:**
- Same specialty list and same gold sets for every route.
- No tuning of keywords or prompt on the gold sets in this round. Any later tuning must use a
  separate split, otherwise the numbers are inflated.
- Every run saves its predictions, metrics, model and prompt version under
  `data/evaluation/results/<run_id>/`.

## 5. Decision rule, fixed before the LLM results

Written down before seeing the LLM numbers, so the choice is not fitted to the results:

1. **Primary metric:** top-1 accuracy on the **independent (Gretel) set**, because it is the
   least biased. In-domain top-1 is the second check.
2. Choose the **LLM or hybrid** over rules only if it is **at least 10 percentage points better**
   on the independent set **and not worse by more than 5 points** in-domain.
3. **Latency limit:** p95 ≤ 10 s warm on our laptop (assumption A2). If it is over, keep the LLM
   only if the accuracy gain is large (≥ 20 points), and plan a faster host.
4. **Between LLM and hybrid:** prefer hybrid if its *high-confidence* answers are ≥ 90% correct.
   Then the confidence label is useful for the clarifying question. Otherwise use plain LLM with
   the rules as fallback only.
5. **Whatever wins:** the emergency red-flag check stays rule-based.

## 6. What the research says

**Papers on LLM specialty routing and triage**
- **LLM workflows for triage, specialty referral and diagnosis**: [npj Digital Medicine 2025](https://www.nature.com/articles/s41746-025-01684-1),
  [medRxiv preprint](https://www.medrxiv.org/content/10.1101/2024.09.27.24314505v1.full.pdf).
  - Benchmarks LLMs on 2,000 MIMIC emergency cases, including **specialty referral**, with
    top-3 suggestions.
  - Retrieval-augmented prompting helped.
  - Symptom-only input (like our patients) is harder than clinician input.
  - Closest to our task.
- **CLARITY**: patient-to-specialist routing, [arXiv 2510.02463](https://www.arxiv.org/pdf/2510.02463v2).
  - Combines a fixed dialogue flow (state machine) with LLM agents.
  - Reports 77% top-1 precision and 96% top-3 recall for specialist routing.
  - Supports returning top-3 and asking follow-up questions.
- **Rare-disease specialty triage with LLMs**: [JMIR / PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC13394855/).
  - Compares 14 LLMs with nurses and non-medical people on initial-visit specialty choice.
  - Notes that most prior work is about urgency triage, not specialty triage.
- **CARE-Bench**: patient-facing triage, [arXiv 2608.03731](https://arxiv.org/html/2608.03731v1).
  - Finds that LLMs still fail at clarification and escalation thresholds.
  - Supports keeping emergency checks rule-based and asking clarifying questions.
- **Symptom checkers vs vignettes**: [Semigran et al., BMJ 2015](https://www.bmj.com/node/900623).
  - 23 symptom checkers on 45 vignettes; triage advice was mostly risk-averse.
  - Also a warning that vignette benchmarks depend on how vignettes are written, which is our
    "author bias" point.

**Methods that could improve the LLM route**
- **Medprompt**: [Nori et al., arXiv 2311.16452](https://arxiv.org/pdf/2311.16452), [code](https://github.com/microsoft/promptbase).
  - Dynamic few-shot: retrieve the k most similar labelled examples by embedding and put them in
    the prompt.
  - Self-generated chain of thought.
  - Choice-shuffle ensemble with majority vote.
  - Dynamic few-shot is cheap for us. Ensembles multiply latency, so they don't fit CPU.
- **Constrained decoding** (our enum): [arXiv 2609.23742](https://arxiv.org/pdf/2609.23742),
  [RANLP 2025](https://aclanthology.org/anthology-files/pdf/ranlp/2025.ranlp-1.124.pdf).
  - Guarantees a valid label, but not the right one.
  - Classification accuracy stays stable for instruction-tuned models.
  - Matches what we saw: valid names always, but a wrong forced pick when the list was too
    short.
- **Fine-tuned small classifier** (e.g. Bio_ClinicalBERT):
  - On MTSamples, a specialty-labelled set of doctors' notes:
    [model card](https://huggingface.co/mnaylor/bioclinical-bert-finetuned-mtsamples),
    [leakage-free benchmark: macro-F1 only about 0.28 on 40 specialties](https://papers.cool/arxiv/2603.22752).
  - Needs thousands of labelled *patient-style* texts, which we don't have. So it's an option for
    later, not now.

**Datasets**

| Dataset | What it is | Use for us |
|---------|------------|------------|
| [gretelai/symptom_to_diagnosis](https://huggingface.co/datasets/gretelai/symptom_to_diagnosis) | 1,065 patient-style symptom texts, 22 diagnoses, Apache-2.0 | **Used now** as the independent test set (diagnosis → specialty mapped) |
| [DDXPlus](https://arxiv.org/abs/2205.09148) | 1.3M synthetic patients, 49 pathologies, structured symptoms, NeurIPS 2022 | Larger test set if we turn structured symptoms into sentences; pathologies map to specialties |
| MTSamples ([BRIDGE benchmark](https://arxiv.org/pdf/2504.19467) lists it) | About 5,000 doctors' transcriptions labelled with about 40 specialties | Good for **report-text** routing (our PDF path), not for patient queries |
| MIMIC-IV-ED (used in the npj paper) | Real ED cases | Needs credentialed access; not for us |
| [ashnaz/refined_symptoms_doctors](https://huggingface.co/datasets/ashnaz/refined_symptoms_doctors) | Symptom → doctor type | Small and undocumented; not recommended |

## 7. Results

**Rules route (run `20261106_003054_rules`):**

| Gold set | n | Top-1 | Acceptable | Top-3 | Macro-F1 | Unclear | p95 |
|----------|---|-------|------------|-------|----------|---------|-----|
| MediRoute (in-domain) | 84 | **83.3%** | 88.1% | 88.1% | 0.880 | 9.5% | < 5 ms |
| Gretel (independent) | 212 | **29.7%** | 45.3% | 50.0% | 0.321 | 17.0% | < 5 ms |

The drop from 83% to 30% is the author-bias effect from §4. The keywords match how we write, not
how other people describe symptoms. For example:
- "body aches and fever" style texts went to **Neurology**, because of the word "headache".
- Asthma descriptions without the word "asthma" went to General Medicine.

**LLM and hybrid:** the run is in progress; numbers will be added here.

## 8. Recommendation and next steps

Pending the LLM results and the decision rule in §5. Once decided:
1. Implement the chosen mode as the API default (`MEDIROUTE_ROUTING_MODE`), with the router built
   once at startup.
2. Test it with unit tests (mocked LLM) plus an end-to-end API test, and re-run the evaluation.
3. Possible improvements, each tested as its own experiment:
   - dynamic few-shot examples (Medprompt-style)
   - fuzzy matching for the rules
   - `qwen2.5:3b` as a second model
