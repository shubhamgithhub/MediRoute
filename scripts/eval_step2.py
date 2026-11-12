"""Evaluate Step 2 (hospital ranking) against baselines: P@K, R@K, NDCG@K (K = 3, 5).

Design: docs/design/step2_evaluation_design.md.

Usage (from the repo root, PYTHONPATH=src):
    python scripts/eval_step2.py pool    # write the (hospital, need) pairs still to grade
    python scripts/eval_step2.py run     # rank with every system, compute metrics, write a report
Options: --gold, --grades, --systems ours,B1,..., --seeds 20, --pool-limit 40, --pool-depth 10

Inputs
    data/evaluation/step2_gold.csv               queries (one speciality + at most one procedure)
    data/evaluation/step2_capability_grades.csv  grades 0-3 per (hospital, speciality, procedure)
Outputs
    pool: data/evaluation/step2_to_grade.csv
    run:  data/evaluation/results/<run_id>_step2/ rankings.csv, per_query.csv, metrics.json, report.md

Relevance of a hospital for a query = its capability grade for the query's need when it is in
the patient's area, else 0. Oracle mode: the gold speciality and procedure go straight to Step 2.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from mediroute.common.locations import resolve_location
from mediroute.common.medical_context import MedicalContext
from mediroute.common.specialties import specialty_names
from mediroute.evaluation import ranking_metrics as rm
from mediroute.hospital_recommendation.retrieval.retrieval_config import EMBEDDING_MODEL_NAME, METADATA_FILE
from mediroute.utils.paths import DATA_DIR, HOSPITALS_FILE, PROJECT_ROOT

EVAL_DIR = DATA_DIR / "evaluation"
GOLD_FILE = EVAL_DIR / "step2_gold.csv"
GRADES_FILE = EVAL_DIR / "step2_capability_grades.csv"
TO_GRADE_FILE = EVAL_DIR / "step2_to_grade.csv"
RESULTS_DIR = EVAL_DIR / "results"

KS = (3, 5)
POOL_DEPTH = 10
ALL_SYSTEMS = ["ours", "B0", "B1", "B2", "B3", "B4", "A1", "A2", "S4", "S5", "S6", "S7"]
V2_SYSTEMS = {"S4": ("rules", False), "S5": ("embeddings", False), "S6": ("llm", False), "S7": ("llm", True)}
LLM_CACHE_FILE = EVAL_DIR / "step2_llm_capability_cache.jsonl"
LLM_BUDGET_USD = 0.40  # stop LLM capability calls beyond this (overnight cap for the whole run: $1)
SYSTEM_LABELS = {
    "ours": "Ours: filter + FAISS + rerank",
    "B0": "B0 random among eligible",
    "B1": "B1 TF-IDF keyword, no filters",
    "B2": "B2 filter, alphabetical",
    "B3": "B3 filter + rule bonuses",
    "B4": "B4 filter + FAISS, no rerank",
    "A1": "A1 ours, website-confirmed only",
    "A2": "A2 ours, no procedure match",
    "S4": "S4 v2: criteria + TOPSIS, capability by rules",
    "S5": "S5 v2: criteria + TOPSIS, capability by embeddings",
    "S6": "S6 v2: criteria + TOPSIS, capability by LLM judge",
    "S7": "S7 v2: S6 + location tiers",
}
CONDENSED_DEPTH = 20  # --judged-only: how deep each system ranks before unjudged hospitals are dropped
GRADE_COLUMNS = ["hospital_id", "hospital_name", "specialty", "procedure", "grade", "evidence_url",
                 "evidence_note", "grader", "graded_on", "confidence", "review_grade", "reviewer"]


# --------------------------------------------------------------------------- inputs

def need_key(specialty: str, procedure: str) -> tuple[str, str]:
    return specialty.strip(), procedure.strip().casefold()


def load_gold(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    names = set(specialty_names())
    for row in rows:
        for col in ("patient_text", "specialty", "procedure", "diagnoses", "preferred_city", "preferred_state",
                    "stratum"):
            row[col] = (row.get(col) or "").strip()
        if row["specialty"] not in names:
            raise ValueError(f"{path.name} {row['query_id']}: unknown speciality {row['specialty']!r}")
        row["need"] = need_key(row["specialty"], row["procedure"])
    return rows


def load_grades(path: Path, metadata: list[dict], judged_only: bool = False) -> dict[tuple[str, str], dict[str, int]]:
    """{need: {hospital_id: grade}}; review_grade overrides grade. Stops if an id's name changed.
    judged_only: keep only grades backed by evidence (a human review, or a draft grade whose website was read,
    confidence high/medium). Low-confidence drafts are fallbacks built from our own hospital data, so they
    cannot judge a change to that data."""
    grades: dict[tuple[str, str], dict[str, int]] = defaultdict(dict)
    if not path.exists():
        return grades
    names = {h["hospital_id"]: h["hospital_name"] for h in metadata}
    problems = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            value = (row.get("review_grade") or "").strip() or (row.get("grade") or "").strip()
            if value == "":
                continue
            reviewed = bool((row.get("review_grade") or "").strip())
            if judged_only and not reviewed and (row.get("confidence") or "").strip() == "low":
                continue
            hid = row["hospital_id"].strip()
            if hid not in names:
                problems.append(f"{hid} not in the hospital data")
            elif row.get("hospital_name", "").strip() and row["hospital_name"].strip() != names[hid]:
                problems.append(f"{hid}: graded as {row['hospital_name']!r}, data says {names[hid]!r}")
            grade = int(value)
            if grade not in (0, 1, 2, 3):
                problems.append(f"{hid}: grade {grade} not in 0-3")
            grades[need_key(row["specialty"], row["procedure"])][hid] = grade
    if problems:
        raise SystemExit("Grades do not match the hospital data (was it rebuilt?):\n  " + "\n  ".join(problems))
    return grades


# --------------------------------------------------------------------------- systems

class Systems:
    """Every system ranks with the engine's own components, so only the method differs."""

    def __init__(self):
        from mediroute.hospital_recommendation.engine import HospitalRecommendationEngine
        from mediroute.hospital_recommendation.retrieval.keyword_retriever import KeywordHospitalRetriever

        self.engine = HospitalRecommendationEngine()
        self.metadata = self.engine.faiss_retriever.metadata
        self.by_position = {h["vector_position"]: h for h in self.metadata}
        self.keyword = KeywordHospitalRetriever()
        self._v2: dict[str, object] = {}

    def v2(self, system: str, q: dict, k: int) -> list[str]:
        """Design v2 (hospital_recommendation/v2): criteria + TOPSIS with one capability method."""
        if system not in self._v2:
            from mediroute.hospital_recommendation.v2.capability import make_capability
            from mediroute.hospital_recommendation.v2.ranker import V2Ranker
            method, tiers = V2_SYSTEMS[system]
            key = f"cap:{method}"
            if key not in self._v2:
                kwargs = {"cache_file": LLM_CACHE_FILE, "budget_usd": LLM_BUDGET_USD} if method == "llm" else {}
                self._v2[key] = make_capability(method, **kwargs)
            self._v2[system] = V2Ranker(self.metadata, self._v2[key], tiers=tiers)
        ranked = self._v2[system].rank(q["specialty"], q["procedure"], q["preferred_city"], q["preferred_state"], k)
        return [r.hospital_id for r in ranked]

    # ---- shared pieces (mirror HospitalRecommendationEngine.recommend)

    def context(self, q: dict) -> MedicalContext:
        return MedicalContext(
            primary_specialty=q["specialty"],
            procedures=[q["procedure"]] if q["procedure"] else [],
            diagnoses=[d.strip() for d in q["diagnoses"].split(";") if d.strip()],
        )

    def area_ids(self, q: dict) -> set[str]:
        """Hospitals in the area the patient chose (all hospitals when no preference)."""
        cities = resolve_location(q["preferred_city"]) if q["preferred_city"] else None
        state = q["preferred_state"].casefold()
        out = set()
        for h in self.metadata:
            if cities is not None:
                if str(h.get("city") or "").strip() not in cities:
                    continue
            elif state and str(h.get("state") or "").strip().casefold() != state:
                continue
            out.add(h["hospital_id"])
        return out

    def eligible(self, q: dict, verified_only: bool = False) -> list[int]:
        f = self.engine.specialty_filter
        specialty = f.normalize_specialty(q["specialty"])
        area = self.area_ids(q)
        positions = []
        for pos in f.filter_positions(self.metadata, specialty):
            h = self.by_position[pos]
            if h["hospital_id"] not in area:
                continue
            if verified_only and f.specialty_evidence(h, specialty) != "website":
                continue
            positions.append(pos)
        return positions

    def _with_evidence(self, hospitals: list[dict], q: dict) -> list[dict]:
        f = self.engine.specialty_filter
        specialty = f.normalize_specialty(q["specialty"])
        for h in hospitals:
            h["specialty_evidence"] = f.specialty_evidence(h, specialty)
        return hospitals

    def pipeline(self, q: dict, k: int, verified_only: bool = False, use_procedures: bool = True) -> list[str]:
        """Filter -> FAISS (3k) -> rerank, as the engine does, with switches for the ablations."""
        positions = self.eligible(q, verified_only)
        if not positions:
            return []
        ctx = self.context(q)
        query = self.engine.semantic_query_builder.build(ctx)
        found = self.engine.filtered_retriever.search(query, positions, top_k=min(3 * k, len(positions)))
        ranked = self.engine.reranker.rerank(self._with_evidence(found, q),
                                             patient_procedures=ctx.procedures if use_procedures else [], top_k=k)
        return [h["hospital_id"] for h in ranked]

    # ---- the systems

    def ours(self, q: dict, k: int) -> list[str]:
        out = self.engine.recommend(self.context(q), preferred_city=q["preferred_city"] or None,
                                    preferred_state=q["preferred_state"] or None, top_k=k)
        return [h["hospital_id"] for h in out["results"]]

    def b0(self, q: dict, k: int, seed: int) -> list[str]:
        ids = sorted(self.by_position[p]["hospital_id"] for p in self.eligible(q))
        random.Random(f"{seed}-{q['query_id']}").shuffle(ids)
        return ids[:k]

    def b1(self, q: dict, k: int) -> list[str]:
        return [h["hospital_id"] for h in self.keyword.search(q["patient_text"], top_k=k)]

    def b2(self, q: dict, k: int) -> list[str]:
        hospitals = sorted((self.by_position[p] for p in self.eligible(q)), key=lambda h: h["hospital_name"])
        return [h["hospital_id"] for h in hospitals[:k]]

    def b3(self, q: dict, k: int) -> list[str]:
        hospitals = sorted((dict(self.by_position[p], semantic_score=0.0) for p in self.eligible(q)),
                           key=lambda h: h["hospital_name"])
        ranked = self.engine.reranker.rerank(self._with_evidence(hospitals, q),
                                             patient_procedures=self.context(q).procedures, top_k=k)
        return [h["hospital_id"] for h in ranked]

    def b4(self, q: dict, k: int) -> list[str]:
        positions = self.eligible(q)
        if not positions:
            return []
        query = self.engine.semantic_query_builder.build(self.context(q))
        return [h["hospital_id"] for h in self.engine.filtered_retriever.search(query, positions, top_k=k)]

    def rank(self, system: str, q: dict, k: int, seed: int = 0) -> list[str]:
        if system == "ours":
            return self.ours(q, k)
        if system == "B0":
            return self.b0(q, k, seed)
        if system == "A1":
            return self.pipeline(q, k, verified_only=True)
        if system == "A2":
            return self.pipeline(q, k, use_procedures=False)
        if system in V2_SYSTEMS:
            return self.v2(system, q, k)
        return getattr(self, system.lower())(q, k)


# --------------------------------------------------------------------------- pool

def procedure_mentioned(h: dict, procedure: str) -> bool:
    text = " ".join(str(h.get(c) or "") for c in ("procedures", "subspecialties", "hospital_search_text"))
    return procedure.casefold() in text.casefold()


def cmd_pool(args, systems: Systems, gold: list[dict]) -> None:
    grades = load_grades(args.grades, systems.metadata)
    by_id = {h["hospital_id"]: h for h in systems.metadata}
    wanted: dict[tuple[str, str, str], set[str]] = defaultdict(set)  # (hid, specialty, procedure) -> query ids
    for q in gold:
        area = systems.area_ids(q)
        if len(area) <= args.pool_limit:
            judged = set(area)  # complete judgements
        else:
            judged = set()
            for system in args.systems:
                for k in sorted({5, args.pool_depth}):
                    judged |= set(systems.rank(system, q, k)) & area
            if q["procedure"]:
                judged |= {hid for hid in area if procedure_mentioned(by_id[hid], q["procedure"])}
        for system in args.systems:  # whatever a system shows is graded, also outside the area
            judged |= set(systems.rank(system, q, 5))
        for hid in judged:
            wanted[(hid, q["specialty"], q["procedure"])].add(q["query_id"])

    todo = [(key, qids) for key, qids in wanted.items() if key[0] not in grades.get(need_key(key[1], key[2]), {})]
    todo.sort(key=lambda item: (item[0][1], item[0][2], by_id[item[0][0]]["city"], item[0][0]))
    with TO_GRADE_FILE.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(GRADE_COLUMNS[:4] + ["city", "official_source_url", "queries"] + GRADE_COLUMNS[4:])
        for (hid, specialty, procedure), qids in todo:
            h = by_id[hid]
            writer.writerow([hid, h["hospital_name"], specialty, procedure, h["city"], h.get("official_source_url", ""),
                             ";".join(sorted(qids))] + [""] * (len(GRADE_COLUMNS) - 4))
    print(f"{len(wanted)} (hospital, need) pairs judged in total; {len(wanted) - len(todo)} already graded.")
    print(f"{len(todo)} still to grade -> {TO_GRADE_FILE.relative_to(PROJECT_ROOT)}")
    print("Grade from the hospital's website (rubric: docs/design/step2_evaluation_design.md section 5), then "
          "append the rows to step2_capability_grades.csv.")


# --------------------------------------------------------------------------- run

def query_metrics(ranked: list[str], rel: dict[str, int], capability: dict[str, int], area: set[str]) -> dict:
    m = {}
    for k in KS:
        m[f"P@{k}"] = rm.precision_at_k(ranked, rel, k)
        m[f"R@{k}"] = rm.recall_at_k(ranked, rel, k)
        m[f"NDCG@{k}"] = rm.ndcg_at_k(ranked, rel, k)
    m["Hit@3"] = rm.hit_at_k(ranked, rel, 3)
    m["Bad@3"] = rm.bad_at_k(ranked, capability, 3)
    m["OffArea@3"] = sum(1 for h in ranked[:3] if h not in area) / 3
    m["MaxP@5"] = rm.max_precision_at_k(rel, 5)
    # suitability first: is a capable hospital (grade >= 2) in the top 3, wherever it is?
    m["Capable@3"] = 1.0 if any(capability.get(h, 0) >= 2 for h in ranked[:3]) else 0.0
    if rm.relevant_count(rel) == 0:  # nothing good to find: only the safety numbers count
        for key in [k for k in m if k.split("@")[0] in ("P", "R", "NDCG", "Hit", "MaxP")]:
            m[key] = None
    return m


METRIC_ORDER = ["NDCG@5", "NDCG@3", "P@3", "P@5", "R@3", "R@5", "Hit@3", "Capable@3", "Bad@3", "OffArea@3", "MaxP@5"]


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def git_info() -> dict:
    def git(*a):
        return subprocess.run(["git", *a], cwd=PROJECT_ROOT, capture_output=True, text=True).stdout.strip()
    return {"commit": git("rev-parse", "--short", "HEAD"), "dirty": bool(git("status", "--porcelain"))}


def fmt(value, ci=None) -> str:
    if value is None:
        return "–"
    text = f"{value:.3f}"
    return f"{text} [{ci[0]:.2f}, {ci[1]:.2f}]" if ci else text


def cmd_run(args, systems: Systems, gold: list[dict]) -> None:
    grades = load_grades(args.grades, systems.metadata, judged_only=args.judged_only)
    if not grades:
        raise SystemExit(f"No grades in {args.grades}. Run `pool`, grade the pairs, then `run`.")
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_step2" + ("_judged" if args.judged_only else "")
    out_dir = RESULTS_DIR / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # sanity: our re-implementation of the engine must give the engine's own ranking
    mismatches = [q["query_id"] for q in gold if systems.pipeline(q, 5) != systems.ours(q, 5)]
    if mismatches:
        print(f"WARNING: pipeline() differs from engine.recommend() for {mismatches}; A1/A2 may not be comparable.")

    rankings, per_query = [], []
    values: dict[str, dict[str, list]] = {s: defaultdict(list) for s in args.systems}  # system -> metric -> per query
    strata: dict[str, dict[str, dict[str, list]]] = defaultdict(lambda: {s: defaultdict(list) for s in args.systems})
    warnings = []
    for q in gold:
        area = systems.area_ids(q)
        capability = grades.get(q["need"], {})
        rel = {hid: g for hid, g in capability.items() if hid in area}
        ungraded_area = area - set(capability)
        if len(area) <= args.pool_limit and ungraded_area:
            warnings.append(f"{q['query_id']}: {len(ungraded_area)} hospitals in the area have no grade (run `pool`)")
        for system in args.systems:
            seeds = range(args.seeds) if system == "B0" else [0]
            runs = []
            for seed in seeds:
                if args.judged_only:  # condensed list: rank deeper, drop hospitals without an evidence grade
                    ranked = [h for h in systems.rank(system, q, CONDENSED_DEPTH, seed) if h in capability][:max(KS)]
                else:
                    ranked = systems.rank(system, q, max(KS), seed)
                runs.append(query_metrics(ranked, rel, capability, area))
                if seed == 0:
                    unjudged = [h for h in ranked if h in area and h not in capability]
                    if unjudged:
                        warnings.append(f"{q['query_id']} {system}: unjudged {unjudged}")
                    for rank, hid in enumerate(ranked, start=1):
                        rankings.append({"query_id": q["query_id"], "system": system, "rank": rank, "hospital_id": hid,
                                         "relevance": rel.get(hid, 0), "capability": capability.get(hid, ""),
                                         "in_area": hid in area})
            merged = {key: rm.mean([r[key] for r in runs]) for key in runs[0]}
            per_query.append({"query_id": q["query_id"], "stratum": q["stratum"], "system": system,
                              "n_relevant": rm.relevant_count(rel), "n_area": len(area), **merged})
            for key, value in merged.items():
                values[system][key].append(value)
                strata[q["stratum"]][system][key].append(value)

    metrics = {"run_id": run_id, "mode": "oracle" + (" · judged-only (condensed lists)" if args.judged_only else ""), "queries": len(gold), "systems": args.systems,
               "embedding_model": EMBEDDING_MODEL_NAME, "b0_seeds": args.seeds, "git": git_info(),
               "data_sha256": {"hospitals.csv": file_sha(HOSPITALS_FILE), "hospital_metadata.json": file_sha(METADATA_FILE),
                               "grades": file_sha(args.grades), "gold": file_sha(args.gold)},
               "overall": {}, "by_stratum": {}, "vs_ours_ndcg5_p": {}}
    for system in args.systems:
        metrics["overall"][system] = {
            key: {"mean": rm.mean(v), "ci95": rm.bootstrap_ci(v), "n": sum(x is not None for x in v)}
            for key, v in values[system].items()}
    for stratum, by_system in sorted(strata.items()):
        metrics["by_stratum"][stratum] = {s: {key: rm.mean(v) for key, v in m.items()} for s, m in by_system.items()}
    if "ours" in args.systems:
        for system in args.systems:
            if system != "ours":
                metrics["vs_ours_ndcg5_p"][system] = rm.paired_permutation_p(values["ours"]["NDCG@5"],
                                                                             values[system]["NDCG@5"])

    with (out_dir / "rankings.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rankings[0]))
        writer.writeheader()
        writer.writerows(rankings)
    with (out_dir / "per_query.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(per_query[0]))
        writer.writeheader()
        writer.writerows(per_query)
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    report = render_report(metrics, warnings)
    (out_dir / "report.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"\nWritten to {out_dir.relative_to(PROJECT_ROOT)}")


def render_report(metrics: dict, warnings: list[str]) -> str:
    systems = metrics["systems"]
    lines = [f"# Step 2 evaluation {metrics['run_id']}", "",
             f"Mode: {metrics['mode']} · queries: {metrics['queries']} · git {metrics['git']['commit']}"
             f"{' (dirty)' if metrics['git']['dirty'] else ''} · hospitals.csv {metrics['data_sha256']['hospitals.csv']}"
             f" · grades {metrics['data_sha256']['grades']}", "",
             "Relevant = grade ≥ 2. Mean [95% bootstrap CI]; queries with no relevant hospital are left out of "
             "P / R / NDCG / Hit. p = paired permutation test of NDCG@5 against Ours.", "",
             "## Overall", "",
             "| System | " + " | ".join(METRIC_ORDER) + " | p (NDCG@5) |",
             "|---|" + "---|" * (len(METRIC_ORDER) + 1)]
    for s in systems:
        row = metrics["overall"][s]
        cells = [fmt(row[m]["mean"], row[m]["ci95"] if m.startswith("NDCG") else None) for m in METRIC_ORDER]
        p = metrics["vs_ours_ndcg5_p"].get(s)
        lines.append(f"| {SYSTEM_LABELS[s]} | " + " | ".join(cells) + f" | {'–' if p is None else f'{p:.3f}'} |")
    lines += ["", "## NDCG@5 by stratum", "", "| Stratum | " + " | ".join(systems) + " |",
              "|---|" + "---|" * len(systems)]
    for stratum, by_system in metrics["by_stratum"].items():
        lines.append(f"| {stratum} | " + " | ".join(fmt(by_system[s]["NDCG@5"]) for s in systems) + " |")
    if warnings:
        lines += ["", "## Warnings", ""] + [f"- {w}" for w in warnings[:50]]
        if len(warnings) > 50:
            lines.append(f"- … and {len(warnings) - 50} more")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- main

def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["pool", "run"])
    parser.add_argument("--gold", type=Path, default=GOLD_FILE)
    parser.add_argument("--grades", type=Path, default=GRADES_FILE)
    parser.add_argument("--systems", default=",".join(ALL_SYSTEMS))
    parser.add_argument("--judged-only", action="store_true",
                        help="score only on grades whose website was read (drop low-confidence fallbacks; condensed lists)")
    parser.add_argument("--seeds", type=int, default=20, help="random orders averaged for B0")
    parser.add_argument("--pool-limit", type=int, default=40,
                        help="grade every hospital in the area when it has at most this many")
    parser.add_argument("--pool-depth", type=int, default=POOL_DEPTH,
                        help="for larger areas, pool each system's top N (plus procedure mentions)")
    args = parser.parse_args(argv)
    args.systems = [s.strip() for s in args.systems.split(",") if s.strip()]
    unknown = set(args.systems) - set(ALL_SYSTEMS)
    if unknown:
        parser.error(f"unknown systems {unknown}; choose from {ALL_SYSTEMS}")
    gold = load_gold(args.gold)
    systems = Systems()
    (cmd_pool if args.command == "pool" else cmd_run)(args, systems, gold)


if __name__ == "__main__":
    sys.exit(main())
