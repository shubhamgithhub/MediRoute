"""How does a general AI chatbot answer the same patient questions as MediRoute?

The general AI gets the patient's own words plus the plain question a patient would ask, with no
system prompt, no hospital list and no tools. Its free-text answer is then turned into data by a
second, cheap model (closed list of our 26 specialities + the hospitals it named), and scored with
the SAME gold sets and website grades as MediRoute:

  Step 1 set (the 100 portal-benchmark messages):  speciality correct / confidently wrong / asked
  Step 2 set (the 45 Step 2 gold requests):         named hospitals that are in our verified list,
                                                    in the patient's area, confirmed capable (grades),
                                                    NDCG@5 on judged hospitals (condensed, as MediRoute)

    PYTHONPATH=src python scripts/compare_general_ai.py ask      # call the general AI (cached)
    PYTHONPATH=src python scripts/compare_general_ai.py pool     # hospitals it named that need a grade
    PYTHONPATH=src python scripts/compare_general_ai.py score    # metrics + report

Spend is capped (--budget, default $0.90 for this test); after 10 answers the script projects the
total and stops if the projection is over the cap. Answers are cached, so reruns cost nothing.
"""
from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import benchmark_step1 as bench  # noqa: E402
import eval_step2 as ev  # noqa: E402
import portal_benchmark as portal  # noqa: E402

from mediroute.common.locations import load_cities, resolve_location  # noqa: E402
from mediroute.common.specialties import specialty_names  # noqa: E402
from mediroute.evaluation import ranking_metrics as rm  # noqa: E402
from mediroute.specialty_routing.step1.ollama_client import OpenRouterClient  # noqa: E402
from mediroute.utils.paths import DATA_DIR, HOSPITALS_FILE, PROJECT_ROOT  # noqa: E402

OUT = DATA_DIR / "evaluation" / "general_ai"
ANSWERS = OUT / "answers.jsonl"
EXTRACTS = OUT / "extracts.jsonl"
GENERAL_MODEL = "google/gemini-4-carbon"
EXTRACT_MODEL = "openai/gpt-6-luna"
GAP_S = 3.3  # OpenRouter: 20 requests/minute per model
QUESTION = "Which medical speciality should I see, and which hospitals would you recommend? Please keep the answer short."
MEDIROUTE = {  # MediRoute's own numbers on the same sets (portal run 20261111_230644; Step 2 judged run)
    "step1": {"correct": 0.85, "wrong": 0.03, "asked": 0.12},
    "step2_run": "20261112_101101_step2_judged",
    # mean LLM cost of a full request (Step 1 + Step 2) in the portal run, from logs/step1_trace.jsonl
    "cost_per_request": 0.00042,
}

EXTRACT_PROMPT = """Below is a chatbot's answer to a patient. Turn it into data; do not add anything that is not in it.

specialty: the ONE medical speciality the answer recommends first, mapped to the closest name in this list,
or "none" if it recommends no speciality: {names}
asked_instead: true if the answer mainly asks the patient for more information instead of recommending.
hospitals: every hospital the answer names, in the order given, with the city it gives (empty if none).

Chatbot answer:
\"\"\"{answer}\"\"\""""
EXTRACT_SCHEMA = {"type": "object", "properties": {
    "specialty": {"type": "string"}, "asked_instead": {"type": "boolean"},
    "hospitals": {"type": "array", "items": {"type": "object", "properties": {
        "name": {"type": "string"}, "city": {"type": "string"}}, "required": ["name", "city"]}}},
    "required": ["specialty", "asked_instead", "hospitals"]}


# ----------------------------------------------------------------------------- queries
def queries() -> list[dict]:
    out = []
    for g in portal.pick_queries(100):
        # same input as the portal test: the message plus the report text when the case has one
        text = g["query"] + (f"\n\nReport: {g['report_text']}" if g.get("report_text") else "")
        out.append({"set": "step1", "id": f"{g['gold_set']}:{g['query_id']}", "text": text,
                    "ok": [g["expected_specialty"], *g["alternatives"]]})
    for q in ev.load_gold(ev.GOLD_FILE):
        out.append({"set": "step2", "id": q["query_id"], "text": q["patient_text"], "gold": q})
    return out


def prompt_for(q: dict) -> str:
    return f"{q['text'].strip()}\n\n{QUESTION}"


def _key(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:20]


def _load(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {r["key"]: r for r in rows if r.get("ok")}


def spent() -> float:
    total = 0.0
    for path in (ANSWERS, EXTRACTS):
        if path.exists():
            total += sum(float(json.loads(line).get("cost") or 0) for line in path.read_text(encoding="utf-8").splitlines())
    return total


# ----------------------------------------------------------------------------- ask
def ask_general(client: OpenRouterClient, prompt: str) -> dict:
    # low reasoning effort: a direct chat answer. (This model rejects "reasoning off" and, by default,
    # spends ~700 hidden thinking tokens per answer: 5x the cost and answers cut off at the token limit.)
    payload = {"model": GENERAL_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": 1200,
               "reasoning": {"effort": "low"}, "usage": {"include": True}}
    for attempt in range(4):
        try:
            body = client._request("/chat/completions", payload)
            usage = body.get("usage") or {}
            text = (body["choices"][0]["message"].get("content") or "").strip()
            return {"ok": bool(text), "answer": text, "cost": float(usage.get("cost") or 0),
                    "in": usage.get("prompt_tokens"), "out": usage.get("completion_tokens"),
                    "error": "" if text else "empty answer"}
        except Exception as error:  # noqa: BLE001
            message = str(error)
            if "429" in message:
                time.sleep(15 * (attempt + 1))
                continue
            return {"ok": False, "error": message[:200], "cost": 0.0}
    return {"ok": False, "error": "rate limited", "cost": 0.0}


def cmd_ask(args) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    client = OpenRouterClient(model=GENERAL_MODEL)
    extractor = OpenRouterClient(model=EXTRACT_MODEL)
    answers, extracts = _load(ANSWERS), _load(EXTRACTS)
    todo = queries()
    new_calls, new_cost, last = 0, 0.0, 0.0
    for i, q in enumerate(todo, 1):
        prompt = prompt_for(q)
        akey = _key(GENERAL_MODEL, prompt)
        if akey not in answers:
            total = spent()
            remaining = sum(1 for x in todo[i - 1:] if _key(GENERAL_MODEL, prompt_for(x)) not in answers)
            projected = total + (new_cost / new_calls) * remaining if new_calls >= 10 else total
            if total >= args.budget or projected > args.budget:
                print(f"STOP: spent ${total:.3f}, projected ${projected:.3f} > cap ${args.budget:.2f}")
                break
            time.sleep(max(0.0, last + GAP_S - time.monotonic()))
            last = time.monotonic()
            rec = {"key": akey, "id": q["id"], "set": q["set"], "model": GENERAL_MODEL, **ask_general(client, prompt)}
            with ANSWERS.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(rec, ensure_ascii=False) + "\n")
            new_calls, new_cost = new_calls + 1, new_cost + rec["cost"]
            if rec["ok"]:
                answers[akey] = rec
            print(f"[{i}/{len(todo)}] {q['id']} ok={rec['ok']} ${rec['cost']:.4f} total ${spent():.3f}", flush=True)
        if akey in answers:
            ekey = _key(EXTRACT_MODEL, answers[akey]["answer"])
            if ekey not in extracts:
                call = extractor.generate_json(EXTRACT_PROMPT.format(names="; ".join(specialty_names()),
                                                                     answer=answers[akey]["answer"]),
                                               EXTRACT_SCHEMA, purpose="general_ai_extract")
                rec = {"key": ekey, "id": q["id"], "ok": call.ok, "parsed": call.parsed, "error": call.error,
                       "cost": float((call.details or {}).get("cost") or 0)}
                with EXTRACTS.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(rec, ensure_ascii=False) + "\n")
                if call.ok:
                    extracts[ekey] = rec
    print(f"answers {len(answers)}/{len(todo)} · total spend ${spent():.3f}")


# ----------------------------------------------------------------------------- hospital matching
GENERIC = {"hospital", "hospitals", "the", "and", "of", "for", "centre", "center", "medical", "research",
           "institute", "super", "speciality", "specialty", "multispeciality", "multi", "ltd", "pvt", "a",
           "india", "sciences", "health", "healthcare", "care", "clinic", "&", "multispecialty", "multispecialities",
           "multispecialties", "superspeciality", "superspecialty", "specialities", "specialties", "hospitalsl"}


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.casefold()) if t not in GENERIC and len(t) > 1}


def city_set(city: str) -> set[str]:
    if not city.strip():
        return set()
    cities = resolve_location(city) or set()
    known = {c.name for c in load_cities()}
    return {c for c in cities if c in known}


def _name_variants(name: str) -> list[str]:
    """'RTIICS (Narayana Health)' -> the full name, the name without the brackets, the bracket text."""
    inner = re.findall(r"\(([^)]*)\)", name)
    outer = re.sub(r"\([^)]*\)", " ", name)
    return [v for v in [name, outer, *inner] if v.strip()]


def match_hospital(name: str, city: str, hospitals: list[dict], area: set[str] | None = None) -> tuple[dict | None, str]:
    """Our hospital the AI meant, or None. Every distinctive word of one name variant must appear in our
    name + city (branch words like 'Andheri' may be missing from the AI's name). Between branches of a
    chain: the AI's city, else the patient's area (the AI often gives a locality such as 'Secunderabad'),
    else the closest spelling."""
    hits: list[dict] = []
    for variant in _name_variants(name):
        wanted = _tokens(variant)
        if wanted:
            hits = [h for h in hospitals if wanted <= _tokens(h["hospital_name"] + " " + h["city"])]
            if hits:
                break
    if not hits:
        return None, "not in our list"
    in_city = [h for h in hits if h["city"] in city_set(city)] if city else []
    in_area = [h for h in hits if area and h["hospital_id"] in area]
    if area is not None and not in_city and not in_area:
        # e.g. "Apollo Hospitals, Guwahati" when we only have Apollo in Indore: the AI means a branch we
        # do not have, not a hospital in the wrong city
        return None, "not in our list (we have a branch elsewhere)"
    pool = in_city or in_area or hits
    best = max(pool, key=lambda h: difflib.SequenceMatcher(None, name.casefold(), h["hospital_name"].casefold()).ratio())
    return best, "matched" if (len(pool) == 1 or in_city or in_area) else "matched (chain, branch guessed)"


def area_ids(q: dict, hospitals: list[dict]) -> set[str]:
    cities = resolve_location(q["preferred_city"]) if q["preferred_city"] else None
    state = q["preferred_state"].casefold()
    return {h["hospital_id"] for h in hospitals
            if (h["city"] in cities if cities is not None else (not state or h["state"].casefold() == state))}


def named_hospitals(extract: dict, hospitals: list[dict], area: set[str] | None = None) -> list[dict]:
    out, seen = [], set()
    for item in (extract.get("hospitals") or [])[:5]:
        h, how = match_hospital(item.get("name", ""), item.get("city", ""), hospitals, area)
        hid = h["hospital_id"] if h else None
        if hid and hid in seen:
            continue
        seen.add(hid)
        out.append({"name": item.get("name", ""), "city": item.get("city", ""), "hospital_id": hid, "how": how})
    return out


def _step2_rows():
    hospitals = list(csv.DictReader(HOSPITALS_FILE.open(encoding="utf-8")))
    answers, extracts = _load(ANSWERS), _load(EXTRACTS)
    rows = []
    for q in queries():
        if q["set"] != "step2":
            continue
        a = answers.get(_key(GENERAL_MODEL, prompt_for(q)))
        e = extracts.get(_key(EXTRACT_MODEL, a["answer"])) if a else None
        parsed = (e or {}).get("parsed") or {}
        rows.append((q, a, parsed, named_hospitals(parsed, hospitals, area_ids(q["gold"], hospitals))))
    return hospitals, rows


def cmd_pool(args) -> None:
    hospitals, rows = _step2_rows()
    by_id = {h["hospital_id"]: h for h in hospitals}
    grades = ev.load_grades(ev.GRADES_FILE, hospitals)
    todo = {}
    for q, _, _, named in rows:
        g = q["gold"]
        for item in named:
            hid = item["hospital_id"]
            if hid and hid not in grades.get(g["need"], {}):
                todo.setdefault((hid, g["specialty"], g["procedure"]), set()).add(q["id"])
    with ev.TO_GRADE_FILE.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(ev.GRADE_COLUMNS[:4] + ["city", "official_source_url", "queries"] + ev.GRADE_COLUMNS[4:])
        for (hid, specialty, procedure), qids in sorted(todo.items()):
            h = by_id[hid]
            writer.writerow([hid, h["hospital_name"], specialty, procedure, h["city"], h.get("official_source_url", ""),
                             ";".join(sorted(qids))] + [""] * (len(ev.GRADE_COLUMNS) - 4))
    print(f"{len(todo)} (hospital, need) pairs named by the general AI still need a grade -> {ev.TO_GRADE_FILE.name}")


# ----------------------------------------------------------------------------- score
def cmd_score(args) -> None:
    answers, extracts = _load(ANSWERS), _load(EXTRACTS)
    names = set(specialty_names())
    s1 = []
    for q in queries():
        if q["set"] != "step1":
            continue
        a = answers.get(_key(GENERAL_MODEL, prompt_for(q)))
        e = extracts.get(_key(EXTRACT_MODEL, a["answer"])) if a else None
        if not e:
            continue
        p = e["parsed"] or {}
        spec = p.get("specialty") if p.get("specialty") in names else None
        asked = bool(p.get("asked_instead")) or spec is None
        s1.append({"id": q["id"], "spec": spec, "ok": (not asked) and spec in q["ok"], "asked": asked, "expected": q["ok"][0],
                   "not_in_our_list": bool(p.get("specialty")) and p.get("specialty") not in names and p.get("specialty") != "none"})
    n1 = len(s1)

    hospitals, rows = _step2_rows()
    grades_all = ev.load_grades(ev.GRADES_FILE, hospitals)
    grades_judged = ev.load_grades(ev.GRADES_FILE, hospitals, judged_only=True)
    s2 = []
    for q, a, p, named in rows:
        if not a:
            continue
        g = q["gold"]
        area = area_ids(g, hospitals)
        cap_all, cap_judged = grades_all.get(g["need"], {}), grades_judged.get(g["need"], {})
        ids = [x["hospital_id"] for x in named if x["hospital_id"]]
        rel = {hid: v for hid, v in cap_judged.items() if hid in area}
        ranked = [h for h in ids if h in cap_judged][:5]  # condensed, as MediRoute's judged-only run
        judged_area = [h for h in ranked if h in area]
        s2.append({"id": q["id"], "stratum": g["stratum"], "named": len(named), "in_list": len(ids),
                   "in_area": sum(1 for h in ids if h in area), "wrong_area": sum(1 for h in ids if h not in area),
                   "capable3": any(cap_all.get(h, 0) >= 2 for h in ids[:3]),
                   "bad3": sum(1 for h in ids[:3] if h in cap_judged and cap_judged[h] == 0),
                   "ndcg5": rm.ndcg_at_k(ranked, rel, 5) if rm.relevant_count(rel) else None,
                   "spec_ok": (p.get("specialty") == g["specialty"]), "named_list": named,
                   "judged_in_area": len(judged_area),
                   "judged_capable": sum(1 for h in judged_area if cap_judged[h] >= 2)})

    tot_named = sum(r["named"] for r in s2)
    ndcgs = [r["ndcg5"] for r in s2 if r["ndcg5"] is not None]
    mr = json.loads((ev.RESULTS_DIR / MEDIROUTE["step2_run"] / "metrics.json").read_text(encoding="utf-8"))["overall"]["ours"]
    # the same measure for MediRoute: its judged-only top 5 (condensed), in-area hospitals with grade >= 2
    mr_rank = list(csv.DictReader((ev.RESULTS_DIR / MEDIROUTE["step2_run"] / "rankings.csv").open(encoding="utf-8")))
    mr_judged = [r for r in mr_rank if r["system"] == "ours" and int(r["rank"]) <= 5 and r["in_area"] == "True"]
    mr_capable_share = sum(int(r["relevance"]) >= 2 for r in mr_judged) / len(mr_judged) if mr_judged else None
    ai_judged = sum(r["judged_in_area"] for r in s2)
    ai_capable_share = sum(r["judged_capable"] for r in s2) / ai_judged if ai_judged else None
    # cost per answer: only the answers used above (not smoke tests or discarded runs)
    used = [answers[k] for k in (_key(GENERAL_MODEL, prompt_for(q)) for q in queries()) if k in answers]
    mean = lambda xs: sum(xs) / len(xs) if xs else None  # noqa: E731
    cost = {"general_ai_per_answer": mean([u["cost"] for u in used]),
            "general_ai_output_tokens": mean([u.get("out") or 0 for u in used]),
            "extractor_per_answer": mean([extracts[_key(EXTRACT_MODEL, u["answer"])]["cost"] for u in used
                                          if _key(EXTRACT_MODEL, u["answer"]) in extracts]),
            "mediroute_per_request": MEDIROUTE["cost_per_request"]}
    summary = {
        "model": GENERAL_MODEL, "extractor": EXTRACT_MODEL, "spend_usd": round(spent(), 4), "when": datetime.now().isoformat(timespec="seconds"),
        "cost": cost,
        "step1": {"n": n1, "correct": sum(r["ok"] for r in s1) / n1 if n1 else None,
                  "confidently_wrong": sum((not r["ok"]) and not r["asked"] for r in s1) / n1 if n1 else None,
                  "asked": sum(r["asked"] for r in s1) / n1 if n1 else None,
                  "wrong_but_emergency": sum((not r["ok"]) and not r["asked"] and r["spec"] == "Emergency Medicine" for r in s1) / n1 if n1 else None,
                  "mediroute": MEDIROUTE["step1"]},
        "step2": {"n": len(s2), "hospitals_named": tot_named,
                  "share_in_our_verified_list": sum(r["in_list"] for r in s2) / tot_named if tot_named else None,
                  "share_in_patient_area": sum(r["in_area"] for r in s2) / tot_named if tot_named else None,
                  "share_in_list_wrong_area": sum(r["wrong_area"] for r in s2) / tot_named if tot_named else None,
                  "capable_at3": sum(r["capable3"] for r in s2) / len(s2) if s2 else None,
                  "bad_at3_count": sum(r["bad3"] for r in s2),
                  "ndcg5_judged": sum(ndcgs) / len(ndcgs) if ndcgs else None, "ndcg5_queries": len(ndcgs),
                  "specialty_ok": sum(r["spec_ok"] for r in s2) / len(s2) if s2 else None,
                  "judged_named_in_area": ai_judged, "share_judged_confirmed_capable": ai_capable_share,
                  "mediroute": {"share_judged_confirmed_capable": mr_capable_share, "judged_shown_in_area": len(mr_judged),
                                "ndcg5_judged": mr["NDCG@5"]["mean"], "capable_at3": mr["Capable@3"]["mean"],
                                "offarea_at3": mr["OffArea@3"]["mean"], "share_in_verified_list": 1.0}},
    }
    run = OUT / datetime.now().strftime("%Y%m%d_%H%M%S")
    run.mkdir(parents=True, exist_ok=True)
    (run / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (run / "step1.json").write_text(json.dumps(s1, indent=1), encoding="utf-8")
    (run / "step2.json").write_text(json.dumps(s2, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"written to {run.relative_to(PROJECT_ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["ask", "pool", "score"])
    parser.add_argument("--budget", type=float, default=0.90, help="USD cap for this test (general AI + extractor)")
    args = parser.parse_args()
    {"ask": cmd_ask, "pool": cmd_pool, "score": cmd_score}[args.command](args)


if __name__ == "__main__":
    main()
