# Base documents

Reference material that drives project decisions. **Read these before changing scope,
architecture or deliverables.**

Team T09: Anand Chavan, Aniket More, Pravin Patil, RaviTeja Karri, Shubham Thakare

| File | What it is |
|------|------------|
| `T09_MediRoute_MidSem_Project_Document.docx` | Our mid-semester report: problem, scope, data, intelligence and evaluation plan (4 Oct 2026) |
| `T09_MediRoute_MidSem_Presentation_v2.0.pptx` | Our mid-semester presentation (5 slides) |
| `Team_9_Feedbacks.docx` | TA's mid-semester review. Overall readiness: **"Needs improvements"** |
| _(to be added)_ | Professor's project documentation guideline |

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
