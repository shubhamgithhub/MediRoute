# Base documents

Reference material that drives project decisions. **Read these before changing scope,
architecture or deliverables.**

Team T09: Anand Chavan, Aniket More, Pravin Patil, RaviTeja Karri, Shubham Thakare

| File | What it is |
|------|------------|
| `T09_MediRoute_MidSem_Project_Document.docx` | Our mid-semester report: problem, scope, data, intelligence and evaluation plan (4 Oct 2026) |
| `T09_MediRoute_MidSem_Presentation_v2.0.pptx` | Our mid-semester presentation (5 slides) |
| `Team_9_Feedbacks.docx` | TA's mid-semester review. Overall readiness: **"Needs improvements"** |
| `capstone_guidelines.pdf` | Course capstone guidelines. **Kept local only (gitignored):** the PDF is watermarked for personal use, so ask the course team for your own copy |

---

## What the course grades (our notes on the capstone guidelines)

- **Final review, 5 Dec 2026, carries 100% of the marks.** It's held on campus: a 20-minute
  presentation, a demo and an individual viva. The marks are roughly equal parts scope and
  impact, technical depth and execution, presentation, and viva.
- **Three layers are expected:** Intelligence (RAG, agent or LangGraph), **Evaluation** (gold
  dataset, metrics, baselines, LLM-as-judge using a *different* model, hallucination and
  faithfulness, latency, cost per query) and **Deployment** (FastAPI serving, containers, CI/CD,
  and an observability dashboard for latency, cost and errors).
- **One thing working end to end beats many half-built features.** Execution and scope are
  graded, not novelty.
- **For a health project, evaluation is mandatory.** The question is whether an expert would
  trust the answers.
- **Viva is about each person's own contribution.** Keep a contribution log from day one.
- **Engineering habits:** version prompts, rules and configs; change one thing per evaluation run;
  keep an experiments log; report negative results.
- **Final checklist:**
  - someone outside the team has used the system
  - evaluation results compared against a baseline
  - deployed, with a dashboard
  - contribution log
  - limitations slide, each with a fix path
  - backup demo recording
  - rehearsed within the time limit
- **Budget:** ₹40,000 per team for APIs, compute or paid data.
- **AI-assisted coding is allowed.** The team must own the design, the architecture, the
  evaluation choices and the interpretation of results, and be able to defend every box in the
  architecture.

---

## What we committed to (mid-sem report + presentation)

- **Problem:** international patients can't easily match a diagnosis to suitable Indian hospitals.
- **Scope:** hospital discovery, report understanding and ranking. It excludes diagnosis,
  treatment prescription and travel booking.
- **Features listed:** diagnosis-based recommendations from a query plus reports, translation,
  currency conversion, a PDF summary, and a hospital-side enquiry agent.
- **Data:** NABH directory for hospitals (synthetic specialty and cost where data is missing,
  marked as such), CGHS rates as the cost proxy, synthetic patient queries and reports, and a
  team-curated diagnosis-to-specialty ground truth.
- **Intelligence:** an LLM extracts the diagnosis, then vector-store retrieval, then re-ranking.
  Cost is displayed but not used for ranking.
- **Initial ranking weights:** medical fit 60%, location 20%, facilities 20%. We said we would
  test these weights.
- **Evaluation promised:** precision and recall against the ground truth, PDF checklist,
  translation quality, latency and API cost.

## What the TA asked for (mid-sem feedback)

**Key message:** the project will be judged on the *reliability, explainability and
demonstrated incremental value* of the AI recommendation engine, not on the number of features.

| Priority | Action |
|----------|--------|
| Critical | **Narrow the scope** to medical-information extraction, diagnosis-to-specialty mapping and explainable hospital ranking |
| Critical | **Verified hospital-specialty dataset.** NABH accreditation alone doesn't prove expertise. Clearly separate real data from simulated data |
| Critical | **Independently reviewed evaluation cases.** Expert-reviewed diagnosis-to-specialty mapping and graded hospital-relevance labels |
| High | **Baselines.** Keyword search, rule-based mapping and specialty filtering vs our LLM/RAG approach |
| High | **Ranking metrics.** Precision@K, Recall@K and NDCG@K. Evaluate extraction separately (accuracy, omission of critical details) |
| High | **Robustness experiments.** Different ranking weights, incomplete queries, noisy reports and ambiguous cases |
| High | Show measurable AI/ML improvement **before** building secondary features |

Other points:
- **Ranking:** prioritise medical suitability and verified specialty over location. Test the
  weights; don't fix them arbitrarily.
- **Defer or deprioritise:** translation and PDF output are secondary. Currency conversion is
  low value. The hospital-side enquiry agent should be deferred.
- **Architecture:** use multi-agent only where it beats a simpler retrieval pipeline.
- **Safety and wording:** keep hospital discovery clearly separate from clinical decisions.
  Don't present indicative costs or hospital suitability as verified medical advice.
- **Privacy:** use synthetic or de-identified records only. Consider India's DPDP Act (consent,
  access control, retention, secure handling of uploaded reports).
- **Roadmap:** needs clear timelines, owners and measurable milestones.
