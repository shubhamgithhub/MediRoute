# Step 1 POC: LLM judge on disagreements (20261111_195850_step1_benchmark_ollama)

Judge `openai/gpt-6-luna` (pinned, reasoning off, prompt `judge_v1`), run twice per case with the candidate order swapped. Step 1 evidence and LLM votes: the Ollama run (`ollama:llama3.2`). Accuracy counts a clarification question as not correct.

## method 4 (hybrid lookup, plain scoring)

### core50 (n=50, disagreements 12)

| Tie-break | Accuracy | Confidently wrong | Asks |
|---|---|---|---|
| T1 ask | 66% | 0% | 34% |
| T2 LLM wins | 74% | 16% | 10% |
| T3 lookup wins | 80% | 10% | 10% |
| **T5 LLM judge (guarded)** | 82% | 2% | 16% |
| Perfect judge (ceiling) | 84% | 0% | 16% |

Judge on 12 disagreements: answered 9, right 8 (89% of its answers); outcomes {'accepted': 9, 'unclear': 3}; failed checks {'judge said unclear': 3}

## C3 (hybrid lookup, weak evidence half + best match per phrase)

### core50 (n=50, disagreements 11)

| Tie-break | Accuracy | Confidently wrong | Asks |
|---|---|---|---|
| T1 ask | 68% | 2% | 30% |
| T2 LLM wins | 76% | 16% | 8% |
| T3 lookup wins | 88% | 4% | 8% |
| **T5 LLM judge (guarded)** | 88% | 2% | 10% |
| Perfect judge (ceiling) | 90% | 2% | 8% |

Judge on 11 disagreements: answered 10, right 10 (100% of its answers); outcomes {'accepted': 10, 'unclear': 1}; failed checks {'judge said unclear': 1}

## Hallucination guards and cost (all variants)

- Judge calls: 32 (failed: 0); reasoning tokens: 0
- Order-swap flips: 0 of 23
- Failed checks: {'judge said unclear': 4}
- Cost: $0.0024 for 15790 tokens

## Judge answered wrongly

| Variant | ID | Expected | Judge | Other candidate | Quote | Reason |
|---|---|---|---|---|---|---|
| M4 | C026 | Pediatric Cardiology | Cardiology | Obstetrics & Gynaecology | Large perimembranous VSD (8 mm) with left-to-right | A VSD with a left-to-right shunt and planned surgical closure is a heart condition, making |