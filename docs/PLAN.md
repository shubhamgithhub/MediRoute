# MediRoute – Delivery Plan (5 Nov → 5 Dec 2026)

**Goal for the final review:** one system that works end to end, with measured evidence that its
AI beats simple baselines. This follows the TA feedback and the capstone guidelines
(`docs/base/README.md`).

## Approach: thin end-to-end version first, then improve and measure

1. **Agree the interfaces first.** Freeze what Step 1 returns, what Step 2 accepts, the one
   canonical specialty list and the gold-set format ([CONTRACTS.md](CONTRACTS.md)). After that,
   all five people can work in parallel without blocking each other.
2. **Build a crude end-to-end version.** Rule-based router → specialty filter + FAISS →
   results page. It is simple, but it works, it can be demoed, and **it is our baseline**.
3. **Build the evaluation script alongside it.** Gold set v1 plus one script that prints the
   metrics for any pipeline version.
4. **Improve one component per change, and measure each change.** Every change gets a version
   name and a row in `EXPERIMENTS.md`, for example "router-v2-llm: accuracy 64% → 78%". This
   becomes our evaluation story for the presentation and the viva.

## Milestones

| Milestone | Dates | Goal | Done when |
|-----------|-------|------|-----------|
| **M0: Plan and interfaces** | 5–7 Nov | Agree how the pieces fit | CONTRACTS.md agreed by all 5; canonical specialty list complete; git workflow set; contribution and experiments logs started |
| **M1: Working baseline** | 8–14 Nov | Thin end-to-end version + measurement | A query in the UI shows ranked hospitals; gold set v1 (≥ 50 queries); the evaluation script prints baseline numbers; Docker runs the app |
| **M2: Improve and measure** | 15–22 Nov | The AI improvements, each one measured | LLM router, ICD-10 mapping, AHP-TOPSIS and explanations each compared with the baseline in EXPERIMENTS.md; CI runs on every PR |
| **M3: Hardening** | 23–29 Nov | Robustness, trust, observability | Noisy and incomplete query experiments, LLM-judge, latency/cost/error dashboard. **Feature freeze on 29 Nov** |
| **M4: Final** | 30 Nov–5 Dec | Presentation | **Code freeze on 2 Dec.** Report, deck with a limitations slide, demo recording, 2 rehearsals |

## Critical path

```
CONTRACTS agreed (M0) ──► Gold set v1 (Anand, Ravi) ──► Evaluation script ──► every M2 experiment
        │
        └──► Step 1 rules mode (Pravin) ──► Step 1 → Step 2 connection (Shubham) ──► results page (Shubham)
```

If the contracts or the gold set slip, every M2 experiment loses its measurement. **These two
come first.**

## Owners (tentative)

| Area | Owner |
|------|-------|
| Step 1: specialty routing | Pravin |
| Step 2: hospital recommendation + frontend | Shubham |
| Data + evaluation | Anand, Ravi |
| Deployment (Docker, CI, dashboard, LangGraph) | Aniket |
| Report generation | Anand |

Task-level detail is in [PROJECT_TRACKER.md](PROJECT_TRACKER.md).

## How we work

- **Git:**
  - `main` is always runnable.
  - Each owner works on a feature branch (`pravin/router-modes`, `shubham/ahp-topsis`, …).
  - Small pull requests; **every PR is reviewed by one other teammate** (this also prepares
    everyone for viva questions).
- **Definition of done** for a task:
  - code + a test
  - an `EXPERIMENTS.md` entry, if it changes a metric
  - a `CONTRIBUTIONS.md` entry
  - the tracker updated
- **Check-ins:** 15 minutes, twice a week (Tue and Fri), going through the tracker. Anything
  blocked for more than 2 days is raised immediately.
- **Versioning:** prompts, keyword rules and ranking weights get named versions
  (`router-v1-rules`, `prompt-v3`, `weights-v2`). Change one thing per evaluation run.
- **Logs:** `docs/CONTRIBUTIONS.md` (who did what) and `docs/EXPERIMENTS.md` (what we tried
  and the result, including negative results). Update them as work happens, not at the end.

## Risks

| Risk | Mitigation |
|------|------------|
| Gold set late, so no measurable story | Start M0; 50 queries first; doctor review later |
| Step 1 results depend on whether Ollama is running | Explicit `routing_mode`; evaluation always pins the mode |
| Verified hospital-specialty data incomplete | Mark real vs synthetic; evaluate only on verified hospitals |
| Integration left to the end | Thin end-to-end version in M1; connect early, improve later |
| LLM cost/latency during evaluation runs | Local Ollama for development; budget hosted API calls for the final runs (₹40k) |
| Live demo fails on the day | Recorded backup demo (M4) |
