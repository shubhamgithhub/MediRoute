"""Patient-facing metrics of the portal's top 5: Precision@5, NDCG@5, Hit@1, Bad@5 (team definition, 2026-11-22).

A hospital is GOOD for a query when all three hold:
    treatment  its NABH scope grade for the gold need is >= 2 (data/evaluation/step2_scope_grades.csv)
    NABH       nabh_status = Accredited and, when we have its scope document, still valid today
    location   in the city / area the patient chose, or in the same state (any city when no preference)
NDCG gain uses the scope grade (3 = service named, 2 = department), one step lower for a same-state hospital.
A hospital without a scope grade is UNKNOWN: it counts as not good and is listed in the report.
Bad@5 = share of queries whose top 5 contains a hospital whose scope lists nothing related (grade 0).

    PYTHONPATH=src .venv/Scripts/python.exe scripts/portal_top5_metrics.py <portal run folder or name>

Rows: the portal end to end (patient text -> Step 1 -> Step 2), the engine given the gold speciality and
procedure (no Step 1), and B0 = random order among the eligible hospitals (20 seeds). No old grades are used.
Output in the run folder: top5_metrics.json, top5_per_query.csv, top5_report.md
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eval_step2 as ev  # noqa: E402
from portal_benchmark import RUNS  # noqa: E402

from mediroute.common.locations import load_cities, resolve_location  # noqa: E402
from mediroute.evaluation import ranking_metrics as rm  # noqa: E402
from mediroute.utils.paths import DATA_DIR, HOSPITALS_FILE  # noqa: E402

SCOPE_GRADES = DATA_DIR / "evaluation" / "step2_scope_grades.csv"
SCOPE_INDEX = DATA_DIR / "evaluation" / "nabh_scope" / "index.csv"
K = 5
GROUPS = {"S1": "Big cities and states (S1–S3)", "S2": "Big cities and states (S1–S3)",
          "S3": "Big cities and states (S1–S3)", "S4": "Small cities (S4)", "S5": "Rare specialities (S5)"}


def load_scope_grades() -> dict[tuple[str, str, str], int | None]:
    with SCOPE_GRADES.open(encoding="utf-8", newline="") as f:
        return {(r["hospital_id"], r["specialty"], r["procedure"].casefold()): (int(r["grade"]) if r["grade"] != "" else None)
                for r in csv.DictReader(f)}


def load_validity() -> dict[str, str]:
    with SCOPE_INDEX.open(encoding="utf-8", newline="") as f:
        return {r["hospital_id"]: r["valid_thru"] for r in csv.DictReader(f) if r["valid_thru"]}


def load_hospital_certificates() -> set[str]:
    """Hospitals whose scope document is a full hospital certificate (H-). Blood bank (BB-), ethics committee (EC-)
    and other certificates say nothing about treatment, so their 'scope' is not evidence (treatment unknown)."""
    with SCOPE_INDEX.open(encoding="utf-8", newline="") as f:
        return {r["hospital_id"] for r in csv.DictReader(f) if r["certificate_no_document"].startswith("H-")}


class Judge:
    """Decides, per query, which hospitals are good and their NDCG gain."""

    def __init__(self, today: str):
        with HOSPITALS_FILE.open(encoding="utf-8-sig", newline="") as f:
            self.hospitals = {r["hospital_id"]: r for r in csv.DictReader(f)}
        self.scope = load_scope_grades()
        self.valid_thru = load_validity()
        self.hospital_certificate = load_hospital_certificates()
        self.today = today
        self.state_of_city = {c.name: c.state for c in load_cities()}

    def nabh_ok(self, hid: str) -> tuple[bool, str]:
        h = self.hospitals.get(hid) or {}
        if h.get("nabh_status") != "Accredited":
            return False, f"NABH {h.get('nabh_status', '?')}"
        thru = self.valid_thru.get(hid)
        if thru and thru < self.today:
            return False, f"NABH certificate expired {thru}"
        return True, ""

    def location(self, hid: str, q: dict) -> str:
        """'area' (city / search area / chosen state / no preference), 'state' (same state as the city), or 'out'."""
        h = self.hospitals.get(hid) or {}
        if q["preferred_city"]:
            cities = resolve_location(q["preferred_city"]) or set()
            if h.get("city") in cities:
                return "area"
            states = {self.state_of_city.get(c) for c in cities}
            return "state" if h.get("state") in states else "out"
        if q["preferred_state"]:
            return "area" if h.get("state", "").casefold() == q["preferred_state"].casefold() else "out"
        return "area"

    def treatment(self, hid: str, q: dict) -> int | None:
        if hid not in self.hospital_certificate:
            return None
        return self.scope.get((hid, q["specialty"], q["procedure"].casefold()))

    def judge(self, hid: str, q: dict) -> dict:
        treat = self.treatment(hid, q)
        nabh, why_nabh = self.nabh_ok(hid)
        loc = self.location(hid, q)
        good = treat is not None and treat >= 2 and nabh and loc != "out"
        gain = (max(1, treat - 1) if loc == "state" else treat) if good else 0
        why = [] if good else [w for w in (
            "treatment unknown (no NABH scope grade)" if treat is None else (f"scope grade {treat}" if treat < 2 else ""),
            why_nabh, "outside city and state" if loc == "out" else "") if w]
        return {"good": good, "gain": gain, "treat": treat, "loc": loc, "why": "; ".join(why)}

    def gains(self, q: dict) -> dict[str, int]:
        """Every hospital's gain for the query (the ideal list for NDCG uses all of them)."""
        return {hid: g for hid in self.hospitals if (g := self.judge(hid, q)["gain"]) > 0}


def query_metrics(ranked: list[str], judged: dict[str, dict], gains: dict[str, int]) -> dict:
    top = ranked[:K]
    exists = len(gains)
    m = {"P@5": sum(judged[h]["good"] for h in top) / K if exists else None,
         "NDCG@5": rm.ndcg_at_k(top, gains, K),
         "Hit@1": (1.0 if top and judged[top[0]]["good"] else 0.0) if exists else None,
         "Bad@5": 1.0 if any(judged[h]["treat"] == 0 for h in top) else 0.0,
         "MaxP@5": min(K, exists) / K if exists else None,
         "unknown@5": sum(judged[h]["treat"] is None for h in top)}
    return m


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run")
    parser.add_argument("--today", default=date.today().isoformat(), help="date for the NABH expiry check")
    parser.add_argument("--seeds", type=int, default=20)
    args = parser.parse_args()
    run = Path(args.run).resolve() if Path(args.run).exists() else RUNS / args.run
    rows = [json.loads(l) for l in (run / "results.jsonl").read_text(encoding="utf-8").splitlines() if l]
    gold = {q["query_id"]: q for q in ev.load_gold(ev.GOLD_FILE)}
    systems = ev.Systems()
    judge = Judge(args.today)

    names = {"portal": "Portal end to end (patient text → Step 1 → Step 2)",
             "reference": "Engine given the gold speciality + procedure (no Step 1)",
             "B0": f"B0 random among eligible ({args.seeds} seeds)"}
    values = {s: defaultdict(list) for s in names}
    groups = defaultdict(lambda: {s: defaultdict(list) for s in names})
    per_query, shown_problems = [], []
    for row in rows:
        q = gold[row["query_id"]]
        gains = judge.gains(q)
        lists = {"portal": [row["hospital_ids"]], "reference": [systems.ours(q, K)],
                 "B0": [systems.b0(q, K, seed) for seed in range(args.seeds)]}
        record = {"query_id": q["query_id"], "stratum": q["stratum"], "need": f"{q['specialty']} | {q['procedure'] or '-'}",
                  "location": q["preferred_city"] or q["preferred_state"] or "anywhere", "good_hospitals_exist": len(gains),
                  "step1_specialty": row["final_specialty"], "step1_ok": row["final_specialty"] == q["specialty"]}
        for system, rankings in lists.items():
            runs = []
            for ranked in rankings:
                judged = {h: judge.judge(h, q) for h in ranked[:K]}
                runs.append(query_metrics(ranked, judged, gains))
            merged = {k: rm.mean([r[k] for r in runs]) for k in runs[0]}
            for k, v in merged.items():
                values[system][k].append(v)
                groups[GROUPS[q["stratum"]]][system][k].append(v)
            record.update({f"{system} {k}": merged[k] for k in ("P@5", "NDCG@5", "Hit@1", "Bad@5")})
        top = row["hospital_ids"][:K]
        record["portal top 5"] = " ; ".join(
            f"{h} {judge.hospitals[h]['hospital_name'][:28]} [{'GOOD' if (j := judge.judge(h, q))['good'] else j['why']}]"
            for h in top)
        for h in top:
            j = judge.judge(h, q)
            if not j["good"]:
                shown_problems.append((q["query_id"], h, judge.hospitals[h]["hospital_name"], j["why"]))
        per_query.append(record)

    summary = {s: {k: {"mean": rm.mean(v), "ci95": rm.bootstrap_ci(v) if k in ("P@5", "NDCG@5") else None,
                       "n": sum(x is not None for x in v)} for k, v in values[s].items()} for s in names}
    p_vs_b0 = {k: rm.paired_permutation_p(values["portal"][k], values["B0"][k]) for k in ("P@5", "NDCG@5")}
    p_vs_ref = {k: rm.paired_permutation_p(values["portal"][k], values["reference"][k]) for k in ("P@5", "NDCG@5")}
    no_good = [r["query_id"] for r in per_query if not r["good_hospitals_exist"]]
    metrics = {"run": run.name, "today": args.today, "queries": len(rows), "summary": summary,
               "groups": {g: {s: {k: rm.mean(v) for k, v in d.items()} for s, d in sd.items()} for g, sd in groups.items()},
               "p_portal_vs_B0": p_vs_b0, "p_portal_vs_reference": p_vs_ref, "no_good_hospital_exists": no_good}
    (run / "top5_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    with (run / "top5_per_query.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(per_query[0]))
        w.writeheader()
        w.writerows(per_query)

    def fmt(stat):
        if stat["mean"] is None:
            return "–"
        ci = stat.get("ci95")
        return f"{stat['mean']:.2f}" + (f" [{ci[0]:.2f}–{ci[1]:.2f}]" if ci else "")

    metric_names = ["P@5", "NDCG@5", "Hit@1", "Bad@5", "MaxP@5"]
    md = [f"# Portal top-5 metrics — {run.name}", "",
          "Good = NABH-scope treatment grade ≥ 2 + NABH accredited and valid on "
          f"{args.today} + same city/area or same state. No old grades used. {len(rows)} queries "
          f"(data/evaluation/step2_gold.csv); {len(no_good)} have no good hospital in our data "
          f"({', '.join(no_good) or 'none'}) and are left out of P@5 / NDCG@5 / Hit@1 (Bad@5 counts all).", "",
          "| System | " + " | ".join(metric_names) + " |", "|---|" + "---|" * len(metric_names)]
    for s, label in names.items():
        md.append(f"| {label} | " + " | ".join(fmt(summary[s][k]) for k in metric_names) + " |")
    md += ["", f"Paired permutation test, portal vs B0: P@5 p = {p_vs_b0['P@5']:.3f}, NDCG@5 p = {p_vs_b0['NDCG@5']:.3f}; "
           f"portal vs reference: P@5 p = {p_vs_ref['P@5']:.3f}, NDCG@5 p = {p_vs_ref['NDCG@5']:.3f}.",
           "", "## By group (portal / reference / B0)", "", "| Group | Queries | P@5 | NDCG@5 | Hit@1 | Bad@5 |",
           "|---|---|---|---|---|---|"]
    for g, sd in sorted(groups.items()):
        n = len(sd["portal"]["Bad@5"])
        cells = []
        for k in ("P@5", "NDCG@5", "Hit@1", "Bad@5"):
            cells.append(" / ".join("–" if rm.mean(sd[s][k]) is None else f"{rm.mean(sd[s][k]):.2f}" for s in names))
        md.append(f"| {g} | {n} | " + " | ".join(cells) + " |")
    reasons = defaultdict(int)
    for *_, why in shown_problems:
        for part in why.split("; "):
            reasons[part.split(" 20")[0] if part.startswith("NABH certificate expired") else part] += 1
    md += ["", "## Why shown hospitals were not good (portal top 5)", "", "| Reason | Times |", "|---|---|"]
    md += [f"| {r} | {n} |" for r, n in sorted(reasons.items(), key=lambda x: -x[1])]
    md += ["", "## Per query (portal)", "", "| Query | Need | Location | Good exist | P@5 | NDCG@5 | Hit@1 | Bad@5 |",
           "|---|---|---|---|---|---|---|---|"]
    for r in per_query:
        cell = lambda v: "–" if v is None else f"{v:.2f}"  # noqa: E731
        md.append(f"| {r['query_id']} | {r['need']} | {r['location']} | {r['good_hospitals_exist']} | "
                  f"{cell(r['portal P@5'])} | {cell(r['portal NDCG@5'])} | {cell(r['portal Hit@1'])} | {cell(r['portal Bad@5'])} |")
    md += ["", "Notes: treatment grades are quotes from the NABH scope taken by an LLM and checked by code (grade set by "
           "code); hospitals without a scope document (not H-/entry-level PDF on the NABH portal) have unknown treatment. "
           "Expiry uses the date printed on the scope document; a renewed certificate would not be seen."]
    (run / "top5_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
