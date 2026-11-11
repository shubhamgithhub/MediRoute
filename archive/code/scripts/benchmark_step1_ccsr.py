"""Step 1 benchmark: CCSR mapping and scoring fixes, one change at a time (no new LLM calls).

Replays a finished scripts/benchmark_step1.py run: the LLM's evidence phrases and its speciality
vote are read from the run's trace, the lookup voter is recomputed. Each row adds one change:

    C0  current lookup (our ICD code ranges), hybrid voter as in method 4 (RRF, summed per phrase)
    C1  CCSR lookup (ICD code -> AHRQ CCSR category -> speciality draft table), same scoring
    C2  C1 + symptom matches count half (CCSR symptom categories, e.g. throat pain, low back pain)
    C3  C2 + each phrase votes only for its best match (weaker partial matches no longer add up);
        runner-up specialities keep a small weight (0.1) so the voter still ranks a top 3

Each variant is scored alone (lookup voter on the LLM evidence) and with the LLM voter using the
method 4 rule (agree -> answer, disagree -> ask). For each variant the "perfect judge" ceiling is
also reported: the accuracy if a tie-break always picked the voter that was right.

    PYTHONPATH=src .venv/Scripts/python.exe scripts/benchmark_step1_ccsr.py data/evaluation/results/<run>

Writes report_ccsr.md and metrics_ccsr.json into the run folder.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import benchmark_step1 as bench  # noqa: E402
from benchmark_step1_replay import CATCH_ALL, RRF_K, SEARCH_K, decide, load_trace  # noqa: E402

from mediroute.specialty_routing.step1 import voters  # noqa: E402
from mediroute.specialty_routing.step1.lookup import LookupEntry, LookupIndex  # noqa: E402
from mediroute.utils.paths import TAXONOMY_DIR  # noqa: E402

CCSR_LOOKUP = TAXONOMY_DIR / "step1_lookup_ccsr_draft.csv"
SYMPTOM_WEIGHT = 0.5
RUNNER_UP_WEIGHT = 0.1
VARIANTS = {
    "C0": ("current", 1.0, False, "C0 current lookup (our ICD ranges)"),
    "C1": ("ccsr", 1.0, False, "C1 + CCSR mapping"),
    "C2": ("ccsr", SYMPTOM_WEIGHT, False, "C2 + symptoms count half"),
    "C3": ("ccsr", SYMPTOM_WEIGHT, True, "C3 + best match per phrase"),
}
PROBES = ["throat pain", "difficulty in talking", "kidney stone", "severe pain on one side of back",
          "chest pain", "type 2 diabetes"]


def load_ccsr_entries() -> tuple[list[LookupEntry], dict[str, str]]:
    entries, kind = [], {}
    with CCSR_LOOKUP.open(encoding="utf-8", newline="") as handle:
        for r in csv.DictReader(handle):
            entries.append(LookupEntry(r["entry_id"], r["source"], r["code"], r["text"], r["specialty"]))
            kind[r["entry_id"]] = r["evidence_type"]
    return entries, kind


class LookupVoter:
    def __init__(self, index: LookupIndex, kind: dict[str, str], symptom_weight: float, best_only: bool) -> None:
        self.index, self.kind = index, kind
        self.symptom_weight, self.best_only = symptom_weight, best_only

    def phrase_hits(self, phrase: str) -> list[tuple[LookupEntry, float]]:
        keyword = [e for e, s in self.index.keyword_search(phrase, k=SEARCH_K) if s >= voters.KEYWORD_MIN_SCORE]
        semantic = [e for e, s in self.index.embedding_search(phrase, k=SEARCH_K) if s >= voters.EMBEDDING_MIN_SCORE]
        fused, entries = {}, {}
        for results in (keyword, semantic):
            for rank, entry in enumerate(results, 1):
                fused[entry.entry_id] = fused.get(entry.entry_id, 0.0) + 1.0 / (RRF_K + rank)
                entries[entry.entry_id] = entry
        out = []
        for entry_id, score in sorted(fused.items(), key=lambda kv: -kv[1])[: voters.HITS_PER_PHRASE]:
            weight = self.symptom_weight if self.kind.get(entry_id) == "symptom" else 1.0
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    run_dir = parser.parse_args().run_dir
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))

    current = LookupIndex()
    current.ensure_embeddings()
    ccsr_entries, ccsr_kind = load_ccsr_entries()
    ccsr = LookupIndex(entries=ccsr_entries)
    ccsr.ensure_embeddings()  # one-time encode, cached by text hash
    voters_by_variant = {
        key: LookupVoter(current if src == "current" else ccsr, {} if src == "current" else ccsr_kind, w, best)
        for key, (src, w, best, _) in VARIANTS.items()
    }

    trace = load_trace(run_dir)
    records = [json.loads(line) for line in (run_dir / "predictions.jsonl").read_text(encoding="utf-8").splitlines()]
    gold = {}
    for name in meta["sets"]:
        for g in bench.load_gold(name):
            gold[(name, g["query_id"])] = g

    systems, labels = [], {}
    for key, (_, _, _, label) in VARIANTS.items():
        systems += [f"{key}_lookup", f"{key}_llm"]
        labels[f"{key}_lookup"] = f"{label} · lookup alone"
        labels[f"{key}_llm"] = f"{label} · + LLM (agree or ask)"
    bench.SYSTEM_LABELS.update(labels)

    ceiling = {key: Counter() for key in VARIANTS}
    rows = []
    for rec in records:
        ours = rec["systems"].get("OURS")
        g = gold.get((rec["gold_set"], rec["query_id"]))
        if not ours or not g:
            continue
        t = trace.get(ours["request_id"], {})
        phrases, llm = t.get("phrases") or [], t.get("llm") or []
        ok = {g["expected_specialty"], *g["alternatives"]}
        systems_out = {}
        for key, voter in voters_by_variant.items():
            h = voter.vote(phrases) if phrases else []
            systems_out[f"{key}_lookup"] = {"pred": h[0] if h else None, "ranked": h, "ms": None}
            pred, decision = decide(h, llm, bool(phrases), ask_if_llm_abstains=False)
            interleaved = [n for pair in zip(h + [None] * 3, llm + [None] * 3) for n in pair if n]
            systems_out[f"{key}_llm"] = {"pred": pred, "ranked": list(dict.fromkeys(([pred] if pred else []) + interleaved))[:3],
                                         "ms": None, "decision": decision, "evidence": ours["evidence"],
                                         "emergency": ours["emergency"], "votes_top1": {"lookup": (h or [None])[0], "LLM": (llm or [None])[0]}}
            # perfect-judge ceiling on disagreements
            c = ceiling[key]
            c[(rec["gold_set"], "n")] += 1
            hv, lv = (h or [None])[0], (llm or [None])[0]
            final = pred
            if pred is None and hv and lv and hv != lv:
                final = hv if hv in ok else lv if lv in ok else None
                c[(rec["gold_set"], "both wrong")] += final is None
            c[(rec["gold_set"], "acc")] += final in ok
            c[(rec["gold_set"], "wrong")] += final is not None and final not in ok
        rows.append({**g, "systems": systems_out})

    metrics = bench.compute_metrics(rows, systems, reference="C3_llm", pipelines=tuple(f"{k}_llm" for k in VARIANTS))
    lines = [f"# Step 1: CCSR mapping and scoring fixes ({meta['run_id']})", "",
             "Same LLM evidence and LLM votes as the benchmark run; only the lookup voter changes. One change per row. "
             "Accuracy counts a clarification question as not correct. The CCSR table is a draft awaiting doctor review.", ""]
    for set_name, m in metrics["by_set"].items():
        lines += [f"## {set_name} (n={m['n']})", "", "| Variant | Accuracy (95% CI) | Recall@3 | NDCG@3 | Macro-F1 | "
                  "Confidently wrong | Asks |", "|---|---|---|---|---|---|---|"]
        for s in systems:
            x = m["systems"][s]
            lines.append(f"| {labels[s]} | {x['acceptable']:.0%} ({x['acceptable_ci95'][0]:.0%}–{x['acceptable_ci95'][1]:.0%}) | "
                         f"{x['top3']:.0%} | {x['ndcg3']:.2f} | {x['macro_f1']:.2f} | {x['confidently_wrong']:.0%} | "
                         f"{bench.fmt(x.get('asked'))} |")
        lines += ["", "Perfect-judge ceiling (+ LLM, tie-break always picks the right voter):", "",
                  "| Variant | Accuracy | Confidently wrong | Disagreements where both voters are wrong |", "|---|---|---|---|"]
        for key, (_, _, _, label) in VARIANTS.items():
            c = ceiling[key]
            n = c[(set_name, "n")]
            lines.append(f"| {label} | {c[(set_name, 'acc')] / n:.0%} | {c[(set_name, 'wrong')] / n:.0%} | "
                         f"{c[(set_name, 'both wrong')]} |")
        lines.append("")

    lines += ["## Probe phrases: top lookup specialities per variant", "", "| Phrase | " + " | ".join(VARIANTS) + " |",
              "|---|" + "---|" * len(VARIANTS)]
    for phrase in PROBES:
        lines.append(f"| {phrase} | " + " | ".join(", ".join(v.vote([phrase])) or "—" for v in voters_by_variant.values()) + " |")
    lines.append(f"| kidney stone + severe pain on one side of back (Q031) | " + " | ".join(
        ", ".join(v.vote(["kidney stone", "severe pain on one side of back"])) for v in voters_by_variant.values()) + " |")
    (run_dir / "report_ccsr.md").write_text("\n".join(lines), encoding="utf-8")
    (run_dir / "metrics_ccsr.json").write_text(json.dumps({"meta": meta, **metrics,
        "ceiling": {k: {f"{a}|{b}": v for (a, b), v in c.items()} for k, c in ceiling.items()}}, indent=2), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
