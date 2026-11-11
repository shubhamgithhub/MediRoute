# Step 1 POC: LLM judge on disagreements (20261111_144211_step1_benchmark_ollama)

Judge `openai/gpt-6-luna` (pinned, reasoning off, prompt `judge_v1`), run twice per case with the candidate order swapped. Step 1 evidence and LLM votes: the Ollama run (`ollama:llama3.2`). Accuracy counts a clarification question as not correct.

## method 4 (current lookup)

### core50 (n=50, disagreements 10)

| Tie-break | Accuracy | Confidently wrong | Asks |
|---|---|---|---|
| T1 ask | 68% | 2% | 30% |
| T2 LLM wins | 74% | 16% | 10% |
| T3 lookup wins | 82% | 8% | 10% |
| **T5 LLM judge (guarded)** | 82% | 2% | 16% |
| Perfect judge (ceiling) | 84% | 2% | 14% |

Judge on 10 disagreements: answered 7, right 7 (100% of its answers); outcomes {'accepted': 7, 'unclear': 3}; failed checks {'judge said unclear': 3}

### mediroute (n=84, disagreements 23)

| Tie-break | Accuracy | Confidently wrong | Asks |
|---|---|---|---|
| T1 ask | 67% | 1% | 32% |
| T2 LLM wins | 77% | 18% | 5% |
| T3 lookup wins | 87% | 8% | 5% |
| **T5 LLM judge (guarded)** | 86% | 4% | 11% |
| Perfect judge (ceiling) | 89% | 1% | 10% |

Judge on 23 disagreements: answered 18, right 16 (89% of its answers); outcomes {'accepted': 18, 'order-swap flip': 3, 'unclear': 2}; failed checks {'judge said unclear': 4}

### gretel (n=212, disagreements 122)

| Tie-break | Accuracy | Confidently wrong | Asks |
|---|---|---|---|
| T1 ask | 34% | 7% | 58% |
| T2 LLM wins | 73% | 26% | 1% |
| T3 lookup wins | 56% | 43% | 1% |
| **T5 LLM judge (guarded)** | 77% | 15% | 8% |
| Perfect judge (ceiling) | 84% | 7% | 8% |

Judge on 122 disagreements: answered 108, right 91 (84% of its answers); outcomes {'accepted': 108, 'order-swap flip': 8, 'unclear': 6}; failed checks {'cited evidence does not support the choice': 1, 'judge said unclear': 12}

## C3 (CCSR + scoring fixes)

### core50 (n=50, disagreements 10)

| Tie-break | Accuracy | Confidently wrong | Asks |
|---|---|---|---|
| T1 ask | 68% | 2% | 30% |
| T2 LLM wins | 74% | 16% | 10% |
| T3 lookup wins | 84% | 6% | 10% |
| **T5 LLM judge (guarded)** | 84% | 2% | 14% |
| Perfect judge (ceiling) | 86% | 2% | 12% |

Judge on 10 disagreements: answered 8, right 8 (100% of its answers); outcomes {'accepted': 8, 'order-swap flip': 1, 'unclear': 1}; failed checks {'judge said unclear': 2}

### mediroute (n=84, disagreements 20)

| Tie-break | Accuracy | Confidently wrong | Asks |
|---|---|---|---|
| T1 ask | 70% | 1% | 29% |
| T2 LLM wins | 77% | 18% | 5% |
| T3 lookup wins | 92% | 4% | 5% |
| **T5 LLM judge (guarded)** | 88% | 2% | 10% |
| Perfect judge (ceiling) | 92% | 1% | 7% |

Judge on 20 disagreements: answered 16, right 15 (94% of its answers); outcomes {'accepted': 16, 'order-swap flip': 4}; failed checks {'judge said unclear': 2}

### gretel (n=212, disagreements 108)

| Tie-break | Accuracy | Confidently wrong | Asks |
|---|---|---|---|
| T1 ask | 37% | 11% | 52% |
| T2 LLM wins | 73% | 26% | 1% |
| T3 lookup wins | 57% | 42% | 1% |
| **T5 LLM judge (guarded)** | 73% | 18% | 8% |
| Perfect judge (ceiling) | 82% | 11% | 7% |

Judge on 108 disagreements: answered 92, right 77 (84% of its answers); outcomes {'order-swap flip': 9, 'accepted': 92, 'unclear': 6, 'check failed': 1}; failed checks {'cited evidence does not support the choice': 2, 'judge said unclear': 11}

## Hallucination guards and cost (all variants)

- Judge calls: 518 (failed: 0); reasoning tokens: 0
- Order-swap flips: 25 of 293
- Failed checks: {'judge said unclear': 34, 'cited evidence does not support the choice': 3}
- Cost: $0.0410 for 277994 tokens

## Judge answered wrongly

| Variant | ID | Expected | Judge | Other candidate | Quote | Reason |
|---|---|---|---|---|---|---|
| M4 | Q051 | Pulmonology | Psychiatry | Cardiology | stop breathing in sleep | The reported breathing pauses during sleep are a sleep problem, matching the Psychiatry ev |
| C3 | Q051 | Pulmonology | Psychiatry | Cardiology | stop breathing in sleep | The reported breathing pauses during sleep match the listed sleep problem evidence for Psy |
| M4 | Q083 | Gastroenterology | Hematology & Bone Marrow Transplant | Dermatology | jaundice, yellow eyes and dark urine | The matching evidence links jaundice and dark urine to blood disorders, including anaemia  |
| C3 | G009 | Orthopaedics | Neurology | Reproductive Medicine | My muscles are weak | The reported muscle weakness matches the supplied neurology evidence. |
| M4 | G012 | Orthopaedics | General Medicine | Orthopaedics | I've been coughing up phlegm and my back hurts. I  | The cough with phlegm, weakness, and disorientation suggests a general illness rather than |
| C3 | G012 | Orthopaedics | General Medicine | Orthopaedics | I've been coughing up phlegm and my back hurts. I  | The respiratory symptom and systemic weakness and disorientation make this a general illne |
| M4 | G019 | Endocrinology | Neurology | General Medicine | tingling and numb | Tingling and numbness in the hands and feet most strongly suggest a nerve-related problem. |
| C3 | G019 | Endocrinology | Neurology | General Medicine | My feet and hands are tingling and numb. | Tingling and numbness in the hands and feet point to a nerve-related problem. |
| M4 | G038 | Cardiology | Neurology | Paediatrics | problems keeping my balance | Balance and concentration problems are best supported by the Neurology evidence. |
| C3 | G038 | Cardiology | Neurology | Paediatrics | problems keeping my balance | The balance and concentration difficulties best fit the neurological evidence. |
| C3 | G063 | Cardiothoracic Surgery | Cardiology | Bariatric Surgery | prominent blood vessels on my calves | The prominent blood vessels are the main stated problem, while being overweight is only th |
| C3 | G065 | Gastroenterology | Pulmonology | General Medicine | chronic bad breath and a sour taste in my mouth, I | The matching evidence lines associate the main reported symptoms with Pulmonology. |
| M4 | G069 | Endocrinology | Ophthalmology | General Medicine | I have lost my sight | The reported loss of sight is the clearest main problem and supports ophthalmology. |
| C3 | G069 | Endocrinology | Ophthalmology | General Medicine | I have lost my sight | The reported loss of sight is the decisive problem and matches the ophthalmology evidence. |
| M4 | G078 | General Medicine | Pulmonology | Gastroenterology | a lot of trouble breathing | The prominent breathing difficulty best fits Pulmonology. |
| M4 | G079 | Gastroenterology | ENT | Gastroenterology | I have trouble swallowing food because my throat f | The main problem is difficulty swallowing with a sensation of throat closure, which best f |
| M4 | G080 | Neurology | Gastroenterology | General Medicine | acid reflux | Acid reflux is the clearest specific problem and directly matches Gastroenterology. |
| C3 | G080 | Neurology | Gastroenterology | General Medicine | acid reflux | Acid reflux is the clearest specific problem and directly matches Gastroenterology. |
| M4 | G082 | General Medicine | Orthopaedics | Paediatrics | severe joint pain | Severe joint pain is the main problem and directly matches Orthopaedics. |
| M4 | G091 | Cardiology | Neurology | Cardiology | the dizziness and lack of balance got a lot worse | Worsening dizziness and lack of balance are the main problem and support Neurology. |
| C3 | G091 | Cardiology | Neurology | Cardiology | the dizziness and lack of balance got a lot worse | The worsening dizziness and lack of balance are neurological symptoms and are the main pro |
| M4 | G114 | General Medicine | Pulmonology | General Medicine | I have a hard time breathing. My chest hurts | The reported breathing difficulty and chest pain make a lung or breathing problem the main |
| M4 | G134 | General Medicine | Neurology | Oncology | metallic taste in my mouth and my sense of taste a | The patient's taste and smell changes are directly matched to Neurology, while the oncolog |
| C3 | G134 | General Medicine | Neurology | Oncology | my sense of taste and smell has changed | The patient's main concern is altered taste and smell, which the evidence maps to Neurolog |
| M4 | G156 | Neurology | Ophthalmology | Gastroenterology | trouble seeing clearly | The reported trouble seeing clearly matches blurred vision, an ophthalmology concern. |
| C3 | G156 | Neurology | Ophthalmology | Neurology | trouble seeing clearly | Trouble seeing clearly directly indicates a vision problem, which best fits Ophthalmology. |
| M4 | G160 | General Medicine | Dermatology | Hematology & Bone Marrow Transplant | rashes on my arms, neck, and legs | The patient reports rashes across multiple areas, which most directly fits Dermatology. |
| C3 | G160 | General Medicine | Dermatology | Hematology & Bone Marrow Transplant | rashes on my arms, neck, and legs | The patient's main concrete problem is rashes across several body areas, which best fits D |
| M4 | G161 | General Medicine | Neurology | Ophthalmology | severe headache | The severe headache is the main problem and best fits Neurology. |
| M4 | G167 | General Medicine | Orthopaedics | Oncology | severe joint pain | Severe joint pain is the clearest main problem and directly matches Orthopaedics. |
| C3 | G167 | General Medicine | Orthopaedics | Oncology | severe joint and muscle pain | The patient's severe joint and muscle pain directly supports Orthopaedics, while no cancer |
| C3 | G171 | Cardiothoracic Surgery | Cardiology | Obstetrics & Gynaecology | My legs have also started to swell and I can see s | The prominent blood vessels and leg swelling best fit a blood-vessel condition within Card |
| M4 | G208 | General Medicine | Orthopaedics | General Medicine | My legs and back pain a lot. | The patient's prominent back pain best matches the orthopaedics evidence. |
| C3 | G208 | General Medicine | Orthopaedics | General Medicine | back pain a lot | The patient's prominent back pain best fits the orthopaedic focus on back pain. |
| M4 | G212 | General Medicine | Neurology | Dermatology | severe headache that feels like pressure in my hea | The severe headache and head pressure are the main problem and best match neurology. |