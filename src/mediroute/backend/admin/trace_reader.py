"""Read logs/step1_trace.jsonl and group events into request histories for the admin page.

Two kinds of ids appear in the file:
* Step 1 ``request_id`` (stages input ... response), one per Step 1 run;
* workflow ``request_id`` (stages ``workflow:*``), one per /api/patient-routing call. The
  ``workflow:step1_route`` event carries ``step1_request_id``, which links the two.

A history is built per Step 1 request, with its workflow (Step 2 and outcome) attached when the
request came through /api/patient-routing. Workflow calls that never reached Step 1 (for example
a blank PDF with no text) are listed too.
"""

from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from pathlib import Path
from threading import Lock
from typing import Any

from mediroute.specialty_routing.step1.trace import TRACE_FILE

_cache: dict[str, Any] = {"mtime": None, "size": None, "histories": []}
_lock = Lock()


def _events(path: Path) -> list[dict]:
    events = []
    if not path.exists():
        return events
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def _first(events: list[dict], stage: str) -> dict:
    return next((e for e in events if e.get("stage") == stage), {})


def _step1_summary(rid: str, events: list[dict]) -> dict:
    inp, out = _first(events, "input"), _first(events, "response")
    decision, summary = _first(events, "decision"), _first(events, "votes_summary")
    # the last check is the final state: the LLM self-harm quote (stage 3a) can add to the rules' result
    emergency = next((e for e in reversed(events) if e.get("stage") == "emergency_check"), {})
    llm_ms = sum(e.get("duration_ms") or 0 for e in events if e.get("stage") == "llm_call")
    text_info = inp.get("patient_text") or {}
    return {
        "request_id": rid,
        "ts": inp.get("ts") or (events[0].get("ts") if events else None),
        "parent_request_id": inp.get("parent_request_id"),
        "text": text_info.get("text") if "text" in text_info else f"<hidden, {text_info.get('length', 0)} chars>",
        "report_chars": inp.get("report_chars", 0),
        "clarification_round": inp.get("clarification_round", 0),
        "clarification_answers": inp.get("clarification_answers") or {},
        "selected_by_user": inp.get("selected_specialty"),
        "emergency": bool(emergency.get("is_emergency")),
        "decision": out.get("decision") or decision.get("method"),
        "suggested_specialty": out.get("suggested_specialty"),
        "evidence": out.get("evidence") or [],
        "votes": summary.get("top1_by_voter") or {},
        "total_ms": out.get("total_ms"),
        "llm_ms": llm_ms,
        "complete": bool(out),
    }


def _workflow_summary(wid: str, events: list[dict]) -> dict:
    by_stage = {e.get("stage"): e for e in events}
    rec = by_stage.get("workflow:recommend_hospitals", {})
    ending = next((s for s in ("workflow:finalize", "workflow:no_hospital_for_specialty",
                               "workflow:location_clarification", "workflow:clarification", "workflow:error")
                   if s in by_stage), None)
    outcome = {
        "workflow:finalize": "hospitals listed",
        "workflow:no_hospital_for_specialty": "no hospital for speciality",
        "workflow:location_clarification": "location question",
        "workflow:clarification": "clarification",
        "workflow:error": "error",
    }.get(ending, "in progress / unknown")
    parse = by_stage.get("workflow:parse_reports", {})
    return {
        "workflow_id": wid,
        "ts": parse.get("ts") or events[0].get("ts"),
        "reports": parse.get("files", 0),
        "report_status": parse.get("status"),
        "step1_request_id": by_stage.get("workflow:step1_route", {}).get("step1_request_id"),
        "step2_status": rec.get("status"),
        "city": rec.get("city"),
        "hospital_count": rec.get("count"),
        "top_hospitals": rec.get("top") or [],
        "ranking": rec.get("ranking") or [],
        "related_specialty": rec.get("related_specialty"),
        "ranking_weights": rec.get("weights") or {},
        "semantic_query": rec.get("semantic_query"),
        "specialty_candidates": rec.get("specialty_candidates"),
        "location_candidates": rec.get("location_candidates"),
        "in_area_count": rec.get("in_area_count"),
        "step2_specialty": rec.get("specialty"),
        "outcome": outcome,
        "clarification_type": by_stage.get("workflow:clarification", {}).get("type"),
    }


def load_histories(path: Path = TRACE_FILE) -> list[dict]:
    """All histories, newest first. Re-parsed only when the trace file changes."""
    stat = path.stat() if path.exists() else None
    key = (stat.st_mtime, stat.st_size) if stat else (None, None)
    with _lock:
        if (_cache["mtime"], _cache["size"]) == key:
            return _cache["histories"]
        events = _events(path)
        step1: dict[str, list[dict]] = defaultdict(list)
        workflows: dict[str, list[dict]] = defaultdict(list)
        for event in events:
            rid = event.get("request_id")
            if not rid:
                continue
            (workflows if str(event.get("stage", "")).startswith("workflow:") else step1)[rid].append(event)

        wf_by_step1 = {}
        histories = []
        for wid, wf_events in workflows.items():
            summary = _workflow_summary(wid, wf_events)
            if summary["step1_request_id"]:
                wf_by_step1[summary["step1_request_id"]] = summary
            else:  # never reached Step 1 (e.g. blank PDF, no text)
                histories.append({"request_id": wid, "ts": summary["ts"], "source": "workflow", "text": "",
                                  "decision": None, "suggested_specialty": None, "evidence": [], "votes": {},
                                  "emergency": False, "total_ms": None, "llm_ms": 0, "complete": True,
                                  "clarification_round": 0, "workflow": summary})
        for rid, s1_events in step1.items():
            if not any(e.get("stage") == "input" for e in s1_events):
                continue  # warm-up or partial lines without an input stage
            summary = _step1_summary(rid, s1_events)
            workflow = wf_by_step1.get(rid)
            summary["source"] = "workflow" if workflow else "analyze"
            summary["workflow"] = workflow
            histories.append(summary)
        histories.sort(key=lambda h: h.get("ts") or "", reverse=True)
        _cache.update(mtime=key[0], size=key[1], histories=histories)
        return histories


def request_detail(request_id: str, path: Path = TRACE_FILE) -> dict | None:
    """Every event of one request: the Step 1 stages and, if any, its workflow stages."""
    histories = load_histories(path)
    history = next((h for h in histories if h["request_id"] == request_id), None)
    if history is None:
        return None
    events = _events(path)
    wid = (history.get("workflow") or {}).get("workflow_id")
    return {
        "summary": history,
        "step1_events": [e for e in events if e.get("request_id") == request_id
                         and not str(e.get("stage", "")).startswith("workflow:")],
        "workflow_events": [e for e in events if wid and e.get("request_id") == wid],
        "related_rounds": [h["request_id"] for h in histories
                           if h["request_id"] != request_id and
                           (h.get("parent_request_id") == request_id or
                            (history.get("parent_request_id") and
                             h.get("parent_request_id") == history["parent_request_id"]) or
                            h["request_id"] == history.get("parent_request_id"))],
    }


def trace_keep() -> int:
    """How many requests the trace keeps (MEDIROUTE_TRACE_KEEP, default 100)."""
    try:
        return max(1, int(os.getenv("MEDIROUTE_TRACE_KEEP", "100")))
    except ValueError:
        return 100


def prune_trace(keep: int | None = None, path: Path = TRACE_FILE) -> dict[str, int]:
    """Keep only the newest ``keep`` request histories in the trace file; delete older lines.

    A history's lines are its Step 1 request id and, if any, its workflow id. Lines with no
    request id or from partial runs (no input stage) are dropped with the old data. The rewrite
    holds the trace logger's lock, so no event is written half-way through it.
    """
    keep = keep or trace_keep()
    if not path.exists():
        return {"kept_requests": 0, "removed_lines": 0}
    histories = load_histories(path)
    if len(histories) <= keep:
        return {"kept_requests": len(histories), "removed_lines": 0}
    ids = set()
    for h in histories[:keep]:
        ids.add(h["request_id"])
        wid = (h.get("workflow") or {}).get("workflow_id")
        if wid:
            ids.add(wid)
    handlers = logging.getLogger("mediroute.step1.trace").handlers
    for handler in handlers:
        handler.acquire()
    try:
        kept, removed = [], 0
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    rid = json.loads(line).get("request_id")
                except (json.JSONDecodeError, AttributeError):
                    rid = None
                if rid in ids:
                    kept.append(line if line.endswith("\n") else line + "\n")
                else:
                    removed += 1
        with path.open("w", encoding="utf-8") as handle:  # in place: the log handler keeps its append handle
            handle.writelines(kept)
    finally:
        for handler in handlers:
            handler.release()
    with _lock:
        _cache.update(mtime=None, size=None, histories=[])
    return {"kept_requests": keep, "removed_lines": removed}
