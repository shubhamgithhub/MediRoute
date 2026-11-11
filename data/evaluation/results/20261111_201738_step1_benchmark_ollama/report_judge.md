# Step 1 POC: LLM judge on disagreements (20261111_201738_step1_benchmark_ollama)

Judge `openai/gpt-6-luna` (pinned, reasoning off, prompt `judge_v1`), run twice per case with the candidate order swapped. Step 1 evidence and LLM votes: the Ollama run (`ollama:llama3.2`). Accuracy counts a clarification question as not correct.

## method 4 (hybrid lookup, plain scoring)

### core50 (n=50, disagreements 13)

| Tie-break | Accuracy | Confidently wrong | Asks |
|---|---|---|---|
| T1 ask | 64% | 0% | 36% |
| T2 LLM wins | 80% | 10% | 10% |
| T3 lookup wins | 80% | 10% | 10% |
| **T5 LLM judge (guarded)** | 86% | 2% | 12% |
| Perfect judge (ceiling) | 88% | 0% | 12% |

Judge on 13 disagreements: answered 12, right 11 (92% of its answers); outcomes {'accepted': 12, 'unclear': 1}; failed checks {'judge said unclear': 1}

## C3 (hybrid lookup, weak evidence half + best match per phrase)

### core50 (n=50, disagreements 12)

| Tie-break | Accuracy | Confidently wrong | Asks |
|---|---|---|---|
| T1 ask | 66% | 2% | 32% |
| T2 LLM wins | 82% | 10% | 8% |
| T3 lookup wins | 88% | 4% | 8% |
| **T5 LLM judge (guarded)** | 88% | 2% | 10% |
| Perfect judge (ceiling) | 90% | 2% | 8% |

Judge on 12 disagreements: answered 11, right 11 (100% of its answers); outcomes {'accepted': 11, 'unclear': 1}; failed checks {'judge said unclear': 1}

## Hallucination guards and cost (all variants)

- Judge calls: 34 (failed: 0); reasoning tokens: 0
- Order-swap flips: 0 of 25
- Failed checks: {'judge said unclear': 2}
- Cost: $0.0025 for 16809 tokens

## Judge answered wrongly

| Variant | ID | Expected | Judge | Other candidate | Quote | Reason |
|---|---|---|---|---|---|---|
| M4 | C026 | Pediatric Cardiology | Cardiology | Obstetrics & Gynaecology | Large perimembranous VSD (8 mm) with left-to-right | A VSD with pulmonary hypertension and advised surgical closure is a heart condition, best  |