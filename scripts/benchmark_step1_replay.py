"""Add method 4 (hybrid lookup voter + LLM) to a finished Step 1 benchmark run, without new LLM calls.

Reads a run of scripts/benchmark_step1.py. From its trace.jsonl it takes, per query, the evidence
phrases the LLM extracted and the LLM's speciality vote. The lookup searches are deterministic, so
they are recomputed locally. Method 4 therefore sees exactly the same LLM outputs as the current
pipeline: any difference comes from the design, not from LLM randomness.

Method 4 (proposed Step 1 design, not in the app yet):

    hybrid lookup voter   per evidence phrase, keyword (TF-IDF) and semantic (MiniLM) results are
                          fused by rank with Reciprocal Rank Fusion (RRF, k=60); specialities are
                          then scored as today (best hit per phrase, summed; General Medicine only
                          if no specialist matched)
    LLM voter             the LLM's pick from the 26 specialities (unchanged)
    decision              both name the same speciality -> answer; they disagree -> ask;
                          no evidence -> ask; agreement on General Medicine -> ask once
                          LLM abstains or fails:  4  = the hybrid voter answers alone
                                                  4b = ask

Usage::

    PYTHONPATH=src .venv/Scripts/python.exe scripts/benchmark_step1_replay.py data/evaluation/results/<run>

Writes predictions_method4.jsonl, metrics_method4.json and report_method4.md into the run folder.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import benchmark_step1 as bench  # noqa: E402

RRF_K = 60
RUNNER_UP_WEIGHT = 0.1
SEARCH_K = 20  # results taken from each search before fusing
CATCH_ALL = "General Medicine"

NEW_SYSTEMS = ["A4_hybrid_llm_evidence", "M4_HYBRID_LLM", "M4b_HYBRID_LLM_ASK"]
MAIN = ["B2_lookup_keyword", "B3_lookup_semantic", "B4_llm_only", "M4_HYBRID_LLM", "M4b_HYBRID_LLM_ASK", "OURS"]
bench.SYSTEM_LABELS.update({
    "A4_hybrid_llm_evidence": "A4 hybrid lookup voter alone, on LLM evidence",
    "M4_HYBRID_LLM": "4 MediRoute: hybrid lookup + LLM",
    "M4b_HYBRID_LLM_ASK": "4b same, but asks when the LLM abstains",
})


def load_trace(run_dir: Path) -> dict[str, dict]:
    by_request: dict[str, dict] = {}
    with (run_dir / "trace.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            event = json.loads(line)
            rec = by_request.setdefault(event["request_id"], {})
            if event["stage"] == "evidence":
                rec["phrases"] = event.get("routing_phrases") or []
            elif event["stage"] == "vote" and event.get("voter") == "V3_llm":
                rec["llm"] = [name for name, _ in event.get("top3") or []]
    return by_request


class HybridVoter:
    """One lookup voter: keyword and semantic search fused by rank (RRF)."""

    def __init__(self, index) -> None:
        from mediroute.specialty_routing.step1 import voters
        self.index = index
        self.voters = voters

    def vote(self, phrases: list[str]) -> list[str]:
        per_phrase = []
        for phrase in phrases:
            keyword = [(e, s) for e, s in self.index.keyword_search(phrase, k=SEARCH_K)
                       if s >= self.voters.KEYWORD_MIN_SCORE]
            semantic = [(e, s) for e, s in self.index.embedding_search(phrase, k=SEARCH_K)
                        if s >= self.voters.EMBEDDING_MIN_SCORE]
            fused: dict[str, float] = {}
            entries = {}
            for results in (keyword, semantic):
                for rank, (entry, _) in enumerate(results, 1):
                    fused[entry.entry_id] = fused.get(entry.entry_id, 0.0) + 1.0 / (RRF_K + rank)
                    entries[entry.entry_id] = entry
            ranked = sorted(fused.items(), key=lambda kv: -kv[1])[: self.voters.HITS_PER_PHRASE]
            per_phrase.append((phrase, [(entries[i], score) for i, score in ranked]))
        top3, _ = self.voters._aggregate(per_phrase, 0.0)  # same scoring as today's voters
        return [name for name, _ in top3]


def _voters():
    from mediroute.specialty_routing.step1 import voters
    return voters


class LookupVoter:
    def __init__(self, index, symptom_weight: float, best_only: bool) -> None:
        self.index = index
        self.symptom_weight, self.best_only = symptom_weight, best_only

    def phrase_hits(self, phrase: str) -> list[tuple[LookupEntry, float]]:
        keyword = [e for e, s in self.index.keyword_search(phrase, k=SEARCH_K) if s >= _voters().KEYWORD_MIN_SCORE]
        semantic = [e for e, s in self.index.embedding_search(phrase, k=SEARCH_K) if s >= _voters().EMBEDDING_MIN_SCORE]
        fused, entries = {}, {}
        for results in (keyword, semantic):
            for rank, entry in enumerate(results, 1):
                fused[entry.entry_id] = fused.get(entry.entry_id, 0.0) + 1.0 / (RRF_K + rank)
                entries[entry.entry_id] = entry
        out = []
        for entry_id, score in sorted(fused.items(), key=lambda kv: -kv[1])[: _voters().HITS_PER_PHRASE]:
            weight = self.symptom_weight if entries[entry_id].evidence_type in ("symptom", "weak") else 1.0
            out.append((entries[entry_id], score * weight))
        return sorted(out, key=lambda h: -h[1])

    def vote(self, phrases: list[str]) -> list[str]:
        totals: dict[str, float] = {}
        for phrase in phrases:
            best: dict[str, float] = {}
            for entry, score in self.phrase_hits(phrase):
                best[entry.specialty] = max(best.get(entry.specialty, 0.0), score)
            if not best:
                continue
            if max(best, key=best.get) == CATCH_ALL:  # a general symptom stays general (as today)
                best = {CATCH_ALL: best[CATCH_ALL]}
            if self.best_only:
                top = max(best.values())
                # specialities of the best match (a CCSR category can map to two) get its full score
                best = {s: (v if v >= top - 1e-12 else v * RUNNER_UP_WEIGHT) for s, v in best.items()}
            for specialty, score in best.items():
                totals[specialty] = totals.get(specialty, 0.0) + score
        if any(s != CATCH_ALL for s in totals):
            totals.pop(CATCH_ALL, None)
        return sorted(totals, key=lambda s: -totals[s])[:3]


def decide(hybrid: list[str], llm: list[str], has_phrases: bool, ask_if_llm_abstains: bool) -> tuple[str | None, str]:
    if not has_phrases:
        return None, "clarification_required"
    h, l = (hybrid or [None])[0], (llm or [None])[0]
    if h and l and h == l:
        best = h
    elif h and not l and not ask_if_llm_abstains:
        best = h
    else:
        return None, "clarification_required"
    if best == CATCH_ALL:
        return None, "clarification_required"  # ask once before settling on General Medicine (as today)
    return best, "majority"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    run_dir = args.run_dir
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    if meta.get("no_llm"):
        raise SystemExit("this run has no LLM outputs to replay")

    from mediroute.specialty_routing.step1.lookup import LookupIndex
    index = LookupIndex()
    index.ensure_embeddings()
    hybrid = HybridVoter(index)
    trace = load_trace(run_dir)

    records = [json.loads(line) for line in (run_dir / "predictions.jsonl").read_text(encoding="utf-8").splitlines()]
    for rec in records:
        ours = rec["systems"].get("OURS")
        if not ours:
            continue
        t = trace.get(ours["request_id"], {})
        phrases, llm = t.get("phrases") or [], t.get("llm") or []
        h = hybrid.vote(phrases) if phrases else []
        rec["systems"]["A4_hybrid_llm_evidence"] = {"pred": h[0] if h else None, "ranked": h, "ms": None}
        for key, ask in (("M4_HYBRID_LLM", False), ("M4b_HYBRID_LLM_ASK", True)):
            pred, decision = decide(h, llm, bool(phrases), ask)
            # candidates offered: the answer first, then the two voters' lists interleaved
            interleaved = [n for pair in zip(h + [None] * 3, llm + [None] * 3) for n in pair if n]
            candidates = list(dict.fromkeys(([pred] if pred else []) + interleaved))
            rec["systems"][key] = {
                "pred": pred, "ranked": candidates[:3], "ms": ours["ms"], "decision": decision,
                "evidence": ours["evidence"], "emergency": ours["emergency"], "request_id": ours["request_id"],
                "votes_top1": {"hybrid": (h or [None])[0], "LLM": (llm or [None])[0]},
            }

    with (run_dir / "predictions_method4.jsonl").open("w", encoding="utf-8") as handle:
        for rec in records:
            handle.write(json.dumps(rec, ensure_ascii=False) + "\n")

    done = {(r["gold_set"], r["query_id"]): r for r in records}
    rows = []
    for name in meta["sets"]:
        gold = bench.load_gold(name)
        gold = gold[: meta["limit"]] if meta.get("limit") else gold
        majority = Counter(g["expected_specialty"] for g in gold).most_common(1)[0][0]
        for g in gold:
            rec = done.get((name, g["query_id"]))
            if rec:
                rec["systems"]["B0_majority"] = {"pred": majority, "ranked": [majority], "ms": 0}
                rows.append({**g, "systems": rec["systems"]})

    systems = bench.SYSTEMS + NEW_SYSTEMS
    metrics = bench.compute_metrics(rows, systems, reference="M4_HYBRID_LLM",
                                    pipelines=("M4_HYBRID_LLM", "M4b_HYBRID_LLM_ASK", "OURS"))
    (run_dir / "metrics_method4.json").write_text(json.dumps({"meta": meta, **metrics}, indent=2), encoding="utf-8")
    bench.write_report(run_dir, {**meta, "run_id": meta["run_id"] + " + method 4 (replay)"}, metrics, rows,
                       main_systems=MAIN, filename="report_method4.md")
    print((run_dir / "report_method4.md").read_text(encoding="utf-8"))
    print(f"Method 4 written to {run_dir}")


if __name__ == "__main__":
    main()
