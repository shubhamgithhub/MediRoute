"""Step 1 benchmark: the full pipeline against baselines and ablations on the gold sets.

Standalone: it imports the Step 1 parts and calls them; it changes no app code or app logs
(the request trace goes to the run folder, not logs/step1_trace.jsonl, so the admin page is not
filled with benchmark requests).

Systems (every one gets the same patient text = query + report):

    B0_majority          always the most common expected speciality of the gold set (floor)
    B1_keyword_rules     speciality keywords counted in the text (old RuleRouter, specialties.csv)
    B2_lookup_keyword    TF-IDF search of the whole text over the lookup list (ICD-10-CM + CGHS
                         + lay terms), specialities scored by summed top-8 hits; no AI
    B3_lookup_semantic   the same with MiniLM embeddings (ML, no LLM)
    B4_llm_only          the LLM picks from the 26 specialities (= voter V3, no grounding)
    A1_v1_llm_evidence   V1 keyword voter on the LLM-extracted evidence phrases
    A2_v2_llm_evidence   V2 embedding voter on the LLM-extracted evidence phrases
    A3_pipeline_no_llm   the full pipeline with the LLM switched off (keyword evidence, V1 + V2)
    OURS                 the full pipeline (evidence -> V1, V2, V3 -> 2-of-3 majority, else ask)

B4, A1 and A2 are read from the OURS run (its debug votes), so they cost no extra LLM calls:
about 2 LLM calls per query in total.

Usage::

    PYTHONPATH=src .venv/Scripts/python.exe scripts/benchmark_step1.py            # all gold sets
    ... scripts/benchmark_step1.py --sets core50 --limit 5                        # smoke test
    ... scripts/benchmark_step1.py --no-llm                                       # skip LLM systems
    ... scripts/benchmark_step1.py --resume data/evaluation/results/<run>          # continue a run

Output in data/evaluation/results/<run_id>/: predictions.jsonl (written as it goes),
predictions.csv, metrics.json, report.md, trace.jsonl.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import os
import statistics
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from mediroute.common.specialties import specialty_names
from mediroute.specialty_routing.step1 import trace as step1_trace
from mediroute.utils.paths import DATA_DIR

GOLD_DIR = DATA_DIR / "evaluation"
GOLD_SETS = {
    "core50": "step1_gold_core50.csv",
    "mediroute": "step1_gold_mediroute.csv",
    "gretel": "step1_gold_gretel.csv",
}
SYSTEMS = ["B0_majority", "B1_keyword_rules", "B2_lookup_keyword", "B3_lookup_semantic", "B4_llm_only",
           "A1_v1_llm_evidence", "A2_v2_llm_evidence", "A3_pipeline_no_llm", "OURS"]
LLM_SYSTEMS = {"B4_llm_only", "A1_v1_llm_evidence", "A2_v2_llm_evidence", "OURS"}
SYSTEM_LABELS = {
    "B0_majority": "B0 most common speciality (floor)",
    "B1_keyword_rules": "B1 keyword rules (specialties.csv)",
    "B2_lookup_keyword": "1 Keyword search (TF-IDF)",
    "B3_lookup_semantic": "2 Semantic search (embeddings)",
    "B4_llm_only": "3 LLM only",
    "A1_v1_llm_evidence": "A1 keyword search on LLM evidence",
    "A2_v2_llm_evidence": "A2 semantic search on LLM evidence",
    "A3_pipeline_no_llm": "A3 3-voter pipeline without LLM",
    "OURS": "Before: current pipeline (3 voters)",
}
TOP_K = 8
MAIN_SYSTEMS = ["B2_lookup_keyword", "B3_lookup_semantic", "B4_llm_only", "OURS"]  # headline table


# ---------------------------------------------------------------------------------- gold data
def load_gold(name: str) -> list[dict]:
    path = GOLD_DIR / GOLD_SETS[name]
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    valid = set(specialty_names())
    for row in rows:
        row["gold_set"] = name
        row["alternatives"] = [a.strip() for a in (row.get("acceptable_alternatives") or "").split(";") if a.strip()]
        unknown = {row["expected_specialty"], *row["alternatives"]} - valid
        if unknown:
            raise ValueError(f"{path.name} {row['query_id']}: unknown speciality {unknown}")
    return rows


def parse_critical(value: str) -> list[tuple[str, str]]:
    """'body_part=heart; condition=atrial fibrillation; procedure=surgery, chemotherapy'."""
    items = []
    for part in (value or "").split(";"):
        if "=" not in part:
            continue
        kind, values = part.split("=", 1)
        items += [(kind.strip(), v.strip()) for v in values.split(",") if v.strip()]
    return items


# ---------------------------------------------------------------------------------- systems
def lookup_vote(results) -> list[str]:
    """Specialities ranked by the summed scores of the top-k lookup hits (plain retrieval)."""
    totals: dict[str, float] = defaultdict(float)
    for entry, score in results:
        if score > 0:
            totals[entry.specialty] += score
    return sorted(totals, key=lambda s: -totals[s])[:3]


def vote_names(vote: dict | None) -> list[str]:
    return [name for name, _ in (vote or {}).get("top3", [])]


class Runner:
    def __init__(self, use_llm: bool) -> None:
        from mediroute.specialty_routing.routes import UNCLEAR, RuleRouter
        from mediroute.specialty_routing.step1.lookup import LookupIndex
        from mediroute.specialty_routing.step1.ollama_client import DisabledLLMClient, make_llm_client
        from mediroute.specialty_routing.step1.pipeline import Step1Pipeline

        self.unclear = UNCLEAR
        self.rules = RuleRouter()
        self.index = LookupIndex()
        self.index.ensure_embeddings()
        self.no_llm = Step1Pipeline(index=self.index, client=DisabledLLMClient())
        self.full = None
        self.model = None
        if use_llm:
            client = make_llm_client()
            self.full = Step1Pipeline(index=self.index, client=client)
            self.full.warm_up(logging.getLogger("benchmark"))
            status = self.full.llm_status()
            if not status["available"]:
                raise SystemExit(f"LLM not available ({status['reason']}); start it or use --no-llm")
            self.model = f"{status.get('provider')}:{status.get('model')}"

    def run_query(self, gold: dict) -> dict:
        from mediroute.specialty_routing.step1.pipeline import Step1Input, compose_text

        inp = Step1Input(text=gold["query"], report_text=gold.get("report_text") or "", debug=True)
        text = compose_text(inp)
        out: dict[str, dict] = {}

        t = time.perf_counter()
        rule = self.rules.route(text)
        out["B1_keyword_rules"] = {"pred": None if rule.primary == self.unclear else rule.primary,
                                   "ranked": rule.ranked, "ms": int((time.perf_counter() - t) * 1000)}
        t = time.perf_counter()
        ranked = lookup_vote(self.index.keyword_search(text, k=TOP_K))
        out["B2_lookup_keyword"] = {"pred": ranked[0] if ranked else None, "ranked": ranked,
                                    "ms": int((time.perf_counter() - t) * 1000)}
        t = time.perf_counter()
        ranked = lookup_vote(self.index.embedding_search(text, k=TOP_K))
        out["B3_lookup_semantic"] = {"pred": ranked[0] if ranked else None, "ranked": ranked,
                                     "ms": int((time.perf_counter() - t) * 1000)}
        out["A3_pipeline_no_llm"] = self._pipeline_result(self.no_llm, inp)

        if self.full:
            ours = self._pipeline_result(self.full, inp)
            out["OURS"] = ours
            votes = ours.pop("_votes")
            for key, voter in (("B4_llm_only", "V3"), ("A1_v1_llm_evidence", "V1"), ("A2_v2_llm_evidence", "V2")):
                names = vote_names(votes.get(voter))
                out[key] = {"pred": names[0] if names else None, "ranked": names, "ms": None,
                            "note": (votes.get(voter) or {}).get("note", "")}
        out["A3_pipeline_no_llm"].pop("_votes", None)
        return out

    @staticmethod
    def _pipeline_result(pipeline, inp) -> dict:
        response = pipeline.analyze(inp)
        votes = (response.get("debug") or {}).get("votes", {})
        candidates: list[str] = []
        for vote in votes.values():
            for name in vote_names(vote):
                if name not in candidates:
                    candidates.append(name)
        pred = response["suggested_specialty"] if response["decision"] == "majority" else None
        ranked = ([pred] if pred else []) + [c for c in candidates if c != pred]
        return {"pred": pred, "ranked": ranked[:3], "ms": response["latency_ms"],
                "decision": response["decision"], "evidence": response["evidence"],
                "emergency": response["emergency"], "request_id": response["request_id"],
                "votes_top1": {k: (vote_names(v) or [None])[0] for k, v in votes.items()},
                "_votes": votes}


# ---------------------------------------------------------------------------------- metrics
def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3)


def mcnemar_p(b: int, c: int) -> float:
    """Exact two-sided McNemar test on the discordant pairs (b: only A right, c: only B right)."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(0, min(b, c) + 1)) / 2 ** n
    return round(min(1.0, 2 * tail), 4)


def macro_f1(pairs: list[tuple[str, str | None]]) -> float:
    f1s = []
    for label in sorted({e for e, _ in pairs}):
        tp = sum(e == label and p == label for e, p in pairs)
        fp = sum(e != label and p == label for e, p in pairs)
        fn = sum(e == label and p != label for e, p in pairs)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * prec * rec / (prec + rec) if prec + rec else 0.0)
    return round(statistics.mean(f1s), 3) if f1s else 0.0


def macro_precision_recall(pairs: list[tuple[str, str | None]]) -> tuple[float, float]:
    """Macro averages over the expected specialities of the set (strict: expected label only).
    Precision of a speciality the method never predicted counts as 0."""
    precisions, recalls = [], []
    for label in sorted({e for e, _ in pairs}):
        tp = sum(e == label and p == label for e, p in pairs)
        predicted = sum(p == label for _, p in pairs)
        actual = sum(e == label for e, _ in pairs)
        precisions.append(tp / predicted if predicted else 0.0)
        recalls.append(tp / actual if actual else 0.0)
    return round(statistics.mean(precisions), 3), round(statistics.mean(recalls), 3)


def relevance(name: str, expected: str, alternatives: list[str]) -> int:
    return 2 if name == expected else 1 if name in alternatives else 0


def ndcg_at_k(ranked: list[str], expected: str, alternatives: list[str], k: int = 3) -> float:
    """Graded NDCG@k: expected speciality = 2, accepted alternative = 1, anything else = 0."""
    dcg = sum(relevance(n, expected, alternatives) / math.log2(i + 2) for i, n in enumerate(ranked[:k]))
    ideal_gains = sorted([2] + [1] * len(alternatives), reverse=True)[:k]
    idcg = sum(g / math.log2(i + 2) for i, g in enumerate(ideal_gains))
    return dcg / idcg if idcg else 0.0


def reciprocal_rank(ranked: list[str], acceptable: set[str], k: int = 3) -> float:
    for i, name in enumerate(ranked[:k]):
        if name in acceptable:
            return 1.0 / (i + 1)
    return 0.0


def pct(values: list[int], q: float) -> int | None:
    values = sorted(v for v in values if v is not None)
    return values[min(len(values) - 1, int(round(q * (len(values) - 1))))] if values else None


def score_system(rows: list[dict], system: str) -> dict:
    items = [(r, r["systems"][system]) for r in rows if system in r["systems"]]
    n = len(items)
    if not n:
        return {}
    exact = [s["pred"] == r["expected_specialty"] for r, s in items]
    ok = [s["pred"] in {r["expected_specialty"], *r["alternatives"]} for r, s in items]
    answered = [s["pred"] is not None for _, s in items]
    top3 = [bool({r["expected_specialty"], *r["alternatives"]} & set(s["ranked"][:3])) for r, s in items]
    wrong = [a and not o for a, o in zip(answered, ok)]
    n_ans = sum(answered)
    lo, hi = wilson(sum(ok), n)
    pairs = [(r["expected_specialty"], s["pred"]) for r, s in items]
    m_prec, m_rec = macro_precision_recall(pairs)
    return {
        "n": n,
        "acceptable": round(sum(ok) / n, 3), "acceptable_ci95": [lo, hi],
        "exact": round(sum(exact) / n, 3),
        "top3": round(sum(top3) / n, 3),  # Recall@3: expected or an alternative among the top 3
        "ndcg3": round(statistics.mean(ndcg_at_k(s["ranked"], r["expected_specialty"], r["alternatives"])
                                       for r, s in items), 3),
        "mrr3": round(statistics.mean(reciprocal_rank(s["ranked"], {r["expected_specialty"], *r["alternatives"]})
                                      for r, s in items), 3),
        "macro_precision": m_prec, "macro_recall": m_rec,
        "asked": round(sum(s.get("decision") == "clarification_required" for _, s in items) / n, 3)
        if any("decision" in s for _, s in items) else None,
        "answered": round(n_ans / n, 3),
        "precision_when_answered": round(sum(o for a, o in zip(answered, ok) if a) / n_ans, 3) if n_ans else None,
        "confidently_wrong": round(sum(wrong) / n, 3),
        "macro_f1": macro_f1([(r["expected_specialty"], s["pred"]) for r, s in items]),
        "latency_p50_ms": pct([s.get("ms") for _, s in items], 0.5),
        "latency_p95_ms": pct([s.get("ms") for _, s in items], 0.95),
    }


def paired(rows: list[dict], a: str, b: str) -> dict:
    both = [r for r in rows if a in r["systems"] and b in r["systems"]]
    def ok(r, s):
        return r["systems"][s]["pred"] in {r["expected_specialty"], *r["alternatives"]}
    only_a = sum(ok(r, a) and not ok(r, b) for r in both)
    only_b = sum(ok(r, b) and not ok(r, a) for r in both)
    return {"n": len(both), "only_ours_right": only_a, "only_baseline_right": only_b, "p_value": mcnemar_p(only_a, only_b)}


def pipeline_detail(rows: list[dict], system: str) -> dict:
    items = [(r, r["systems"][system]) for r in rows if system in r["systems"]]
    if not items:
        return {}
    decisions = Counter(s["decision"] for _, s in items)
    detail = {"decisions": dict(decisions),
              "clarification_rate": round(decisions.get("clarification_required", 0) / len(items), 3)}
    # when it asks: would the patient's answer have been needed? candidates contain the right one?
    asked = [(r, s) for r, s in items if s["pred"] is None]
    if asked:
        detail["asked_and_right_in_candidates"] = round(
            sum(r["expected_specialty"] in s["ranked"][:3] for r, s in asked) / len(asked), 3)
    flagged = [(r, s) for r, s in items if (r.get("expects_clarification") or "").lower() in {"true", "false"}]
    if flagged:
        vague = [s for r, s in flagged if r["expects_clarification"].lower() == "true"]
        clear = [(r, s) for r, s in flagged if r["expects_clarification"].lower() == "false"]
        detail["vague_cases_asked"] = f"{sum(s['pred'] is None for s in vague)}/{len(vague)}"
        detail["clear_cases_answered_correctly"] = (
            f"{sum(s['pred'] in {r['expected_specialty'], *r['alternatives']} for r, s in clear)}/{len(clear)}")
    return detail


def extraction_scores(rows: list[dict], system: str) -> dict:
    """Critical-detail recall: share of gold critical details found in the kept evidence."""
    from mediroute.specialty_routing.step1.evidence import _tokens, verify_phrase

    found, total, missed = Counter(), Counter(), []
    for r in rows:
        s = r["systems"].get(system)
        details = parse_critical(r.get("critical_details") or "")
        if not s or not details:
            continue
        tokens = set(_tokens(" ".join(s.get("evidence") or [])))
        for kind, value in details:
            total[kind] += 1
            if verify_phrase(value, tokens)[0]:
                found[kind] += 1
            else:
                missed.append(f"{r['query_id']} {kind}={value}")
    if not total:
        return {}
    by_kind = {k: f"{found[k]}/{total[k]} ({found[k] / total[k]:.0%})" for k in sorted(total)}
    all_found, all_total = sum(found.values()), sum(total.values())
    return {"recall": round(all_found / all_total, 3), "omission_rate": round(1 - all_found / all_total, 3),
            "by_kind": by_kind, "missed": missed}


def emergency_scores(rows: list[dict], system: str) -> dict:
    items = [(r, r["systems"][system]) for r in rows
             if system in r["systems"] and (r.get("emergency") or "").lower() in {"true", "false"}]
    if not items:
        return {}
    pos = [s["emergency"] for r, s in items if r["emergency"].lower() == "true"]
    neg = [s["emergency"] for r, s in items if r["emergency"].lower() == "false"]
    return {"emergencies": len(pos), "caught": sum(pos), "recall": round(sum(pos) / len(pos), 3) if pos else None,
            "non_emergencies": len(neg), "false_alarms": sum(neg),
            "missed": [r["query_id"] for r, s in items if r["emergency"].lower() == "true" and not s["emergency"]]}


# ---------------------------------------------------------------------------------- report
def fmt(v, as_pct=True):
    if v is None:
        return "—"
    return f"{v:.0%}" if as_pct else str(v)


def _metric_table(m: dict, systems: list[str]) -> list[str]:
    lines = ["| Method | Accuracy (95% CI) | Recall@3 | NDCG@3 | MRR@3 | Macro precision | Macro recall | "
             "Macro-F1 | Confidently wrong | Asks |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for system in systems:
        s = m["systems"].get(system)
        if not s:
            continue
        ci = s["acceptable_ci95"]
        lines.append(f"| {SYSTEM_LABELS[system]} | {s['acceptable']:.0%} ({ci[0]:.0%}–{ci[1]:.0%}) | {s['top3']:.0%} | "
                     f"{s['ndcg3']:.2f} | {s['mrr3']:.2f} | {s['macro_precision']:.2f} | {s['macro_recall']:.2f} | "
                     f"{s['macro_f1']:.2f} | {s['confidently_wrong']:.0%} | {fmt(s.get('asked'))} |")
    return lines


def write_report(out_dir: Path, meta: dict, metrics: dict, rows: list[dict], main_systems: list[str] | None = None,
                 filename: str = "report.md") -> None:
    """main_systems go in the headline table; every other scored system goes in the appendix."""
    all_systems = list(next(iter(metrics["by_set"].values()))["systems"])
    main_systems = [s for s in (main_systems or all_systems) if s in all_systems]
    appendix = [s for s in all_systems if s not in main_systems]
    lines = [f"# Step 1 benchmark: {meta['run_id']}", "",
             f"LLM `{meta['llm'] or 'none'}` · gold sets {', '.join(meta['sets'])} · {meta['queries']} queries · "
             f"started {meta['started']}", "",
             "## How to read the metrics", "",
             "- **Accuracy (P@1)**: the top answer is the expected speciality or a listed alternative. A method that "
             "asks a clarification question or abstains counts as not correct, so the pipelines are scored before the "
             "patient answers. 95% CI = Wilson interval.",
             "- **Recall@3**: the expected speciality or an alternative is among the top 3 candidates (also when the "
             "method asks; the candidates are what it offers).",
             "- **NDCG@3**: ranking quality of the top 3; relevance expected = 2, alternative = 1, other = 0.",
             "- **MRR@3**: 1 / rank of the first acceptable speciality (0 if not in the top 3).",
             "- **Macro precision / recall / F1**: per expected speciality, then averaged, so rare specialities count "
             "as much as common ones; strict (expected label only).",
             "- **Confidently wrong**: answered with an unacceptable speciality, the unsafe outcome. **Asks**: share "
             "of queries where the pipeline asks a clarification question.", ""]
    for set_name, m in metrics["by_set"].items():
        lines += [f"## {set_name} (n={m['n']})", ""] + _metric_table(m, main_systems)
        ref = m.get("reference")
        if m.get("paired"):
            lines += ["", f"{SYSTEM_LABELS[ref]} against each method, same queries (McNemar exact test on accuracy):", "",
                      "| Compared with | Only it right | Only the other right | p-value |", "|---|---|---|---|"]
            for system in main_systems + appendix:
                p = m["paired"].get(system)
                if p:
                    lines.append(f"| {SYSTEM_LABELS[system]} | {p['only_ours_right']} | {p['only_baseline_right']} | "
                                 f"{p['p_value']} |")
        for system, d in m["pipeline"].items():
            if d:
                lines += ["", f"{SYSTEM_LABELS[system]}: decisions {d['decisions']}, clarification rate "
                          f"{d['clarification_rate']:.0%}"
                          + (f", acceptable speciality among the candidates when it asked: {d['asked_and_right_in_candidates']:.0%}"
                             if "asked_and_right_in_candidates" in d else "")
                          + (f", vague cases asked {d['vague_cases_asked']}, clear cases answered correctly "
                             f"{d['clear_cases_answered_correctly']}" if "vague_cases_asked" in d else "")]
        e = m["extraction"].get("OURS")
        if e:
            lines += ["", f"Evidence extraction by the LLM (shared by the pipelines): critical-detail recall "
                      f"{e['recall']:.0%} (omission {e['omission_rate']:.0%}); by kind {e['by_kind']}"]
        e = m["emergency"].get("OURS") or next((v for v in m["emergency"].values() if v), None)
        if e:
            lines += ["", f"Emergency rules: caught {e['caught']}/{e['emergencies']} emergencies, "
                      f"{e['false_alarms']} false alarms in {e['non_emergencies']} non-emergencies"
                      + (f", missed {e['missed']}" if e["missed"] else "")]
        lines.append("")

    if appendix:
        lines += ["## Appendix: other baselines and ablations", ""]
        for set_name, m in metrics["by_set"].items():
            lines += [f"### {set_name}", ""] + _metric_table(m, appendix) + [""]

    focus = next(iter(metrics["by_set"].values())).get("reference") or "OURS"
    errors = [r for r in rows if focus in r["systems"] and r["systems"][focus]["pred"] is not None
              and r["systems"][focus]["pred"] not in {r["expected_specialty"], *r["alternatives"]}]
    if errors:
        lines += [f"## {SYSTEM_LABELS[focus]}: confidently wrong (all sets)", "",
                  "| Set | ID | Expected | Answered | Evidence | Votes |", "|---|---|---|---|---|---|"]
        for r in errors:
            s = r["systems"][focus]
            lines.append(f"| {r['gold_set']} | {r['query_id']} | {r['expected_specialty']} | {s['pred']} | "
                         f"{'; '.join(s.get('evidence') or [])[:90]} | {s.get('votes_top1', '')} |")
        lines.append("")
    (out_dir / filename).write_text("\n".join(lines), encoding="utf-8")


def compute_metrics(rows: list[dict], systems: list[str], reference: str = "OURS",
                    pipelines: tuple[str, ...] = ("OURS", "A3_pipeline_no_llm")) -> dict:
    """Scores per gold set; `reference` is compared with every other system (McNemar)."""
    by_set = {}
    pipelines = tuple(p for p in pipelines if p in systems)
    for set_name in dict.fromkeys(r["gold_set"] for r in rows):
        subset = [r for r in rows if r["gold_set"] == set_name]
        sys_scores = {s: score_system(subset, s) for s in systems}
        by_set[set_name] = {
            "n": len(subset),
            "systems": sys_scores,
            "reference": reference,
            "paired": {s: paired(subset, reference, s) for s in systems if s != reference and sys_scores.get(s)}
            if sys_scores.get(reference) else {},
            "pipeline": {s: pipeline_detail(subset, s) for s in pipelines},
            "extraction": {s: extraction_scores(subset, s) for s in pipelines},
            "emergency": {s: emergency_scores(subset, s) for s in pipelines},
        }
    return {"by_set": by_set}


# ---------------------------------------------------------------------------------- main
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--sets", nargs="+", default=list(GOLD_SETS), choices=list(GOLD_SETS))
    parser.add_argument("--limit", type=int, default=0, help="first N queries per set (smoke test)")
    parser.add_argument("--no-llm", action="store_true", help="only the systems that need no LLM")
    parser.add_argument("--resume", type=Path, help="run folder to continue (skips queries already done)")
    args = parser.parse_args()

    if args.resume:
        out_dir = args.resume
        meta = json.loads((out_dir / "meta.json").read_text(encoding="utf-8"))
    else:
        tag = "no-llm" if args.no_llm else os.getenv("MEDIROUTE_LLM_PROVIDER", "ollama")
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + f"_step1_benchmark_{tag}"
        out_dir = GOLD_DIR / "results" / run_id
        out_dir.mkdir(parents=True, exist_ok=True)
        meta = {"run_id": run_id, "sets": args.sets, "limit": args.limit, "no_llm": args.no_llm,
                "started": datetime.now().isoformat(timespec="seconds")}

    step1_trace.TRACE_FILE = out_dir / "trace.jsonl"  # keep benchmark requests out of the admin page
    logging.getLogger("mediroute").setLevel(logging.WARNING)

    runner = Runner(use_llm=not meta["no_llm"])
    meta["llm"] = runner.model
    systems = [s for s in SYSTEMS if not (meta["no_llm"] and s in LLM_SYSTEMS)]

    gold_rows = []
    for name in meta["sets"]:
        rows = load_gold(name)
        gold_rows += rows[: meta["limit"]] if meta["limit"] else rows
    meta["queries"] = len(gold_rows)
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    pred_file = out_dir / "predictions.jsonl"
    done = {}
    if pred_file.exists():
        for line in pred_file.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            done[(rec["gold_set"], rec["query_id"])] = rec
    majority = {name: Counter(r["expected_specialty"] for r in gold_rows if r["gold_set"] == name).most_common(1)[0][0]
                for name in meta["sets"]}

    started = time.perf_counter()
    with pred_file.open("a", encoding="utf-8") as handle:
        todo = [g for g in gold_rows if (g["gold_set"], g["query_id"]) not in done]
        for i, gold in enumerate(todo, 1):
            systems_out = runner.run_query(gold)
            rec = {"gold_set": gold["gold_set"], "query_id": gold["query_id"], "systems": systems_out}
            handle.write(json.dumps(rec, ensure_ascii=False) + "\n")
            handle.flush()
            done[(gold["gold_set"], gold["query_id"])] = rec
            ours = systems_out.get("OURS") or systems_out["A3_pipeline_no_llm"]
            eta = (time.perf_counter() - started) / i * (len(todo) - i)
            print(f"[{i}/{len(todo)}] {gold['gold_set']} {gold['query_id']} expected={gold['expected_specialty']} "
                  f"ours={ours['pred'] or ours['decision']} ({ours['ms']} ms, eta {eta / 60:.0f} min)", flush=True)

    rows = []
    for gold in gold_rows:
        rec = done[(gold["gold_set"], gold["query_id"])]
        rec["systems"]["B0_majority"] = {"pred": majority[gold["gold_set"]], "ranked": [majority[gold["gold_set"]]], "ms": 0}
        rows.append({**gold, "systems": rec["systems"]})

    metrics = compute_metrics(rows, systems)
    meta["finished"] = datetime.now().isoformat(timespec="seconds")
    (out_dir / "metrics.json").write_text(json.dumps({"meta": meta, **metrics}, indent=2), encoding="utf-8")
    with (out_dir / "predictions.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["gold_set", "query_id", "case_type", "expected", "alternatives", *systems,
                         "ours_decision", "ours_evidence", "query"])
        for r in rows:
            s = r["systems"]
            writer.writerow([r["gold_set"], r["query_id"], r.get("case_type", ""), r["expected_specialty"],
                             ";".join(r["alternatives"]), *[(s.get(x) or {}).get("pred") or "" for x in systems],
                             (s.get("OURS") or {}).get("decision", ""), "; ".join((s.get("OURS") or {}).get("evidence", [])),
                             r["query"]])
    write_report(out_dir, meta, metrics, rows, MAIN_SYSTEMS)
    print((out_dir / "report.md").read_text(encoding="utf-8"))
    print(f"Results in {out_dir}")


if __name__ == "__main__":
    main()
