"""Admin API: request history from the Step 1 / workflow trace (logs/step1_trace.jsonl).

NO AUTHENTICATION YET (planned). These endpoints expose redacted patient text, prompts and model
outputs, so the API must stay on localhost (the default 127.0.0.1 binding) until auth is added.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from mediroute.backend.admin.trace_reader import load_histories, request_detail

router = APIRouter(tags=["Admin (no auth yet, local only)"])


@router.get("/api/admin/requests")
def list_requests(
    limit: int = Query(100, ge=1, le=1000),
    q: str = Query("", description="Text to search in the patient message, speciality or request id"),
    decision: str = Query("", description="agreement | judge | lookup_only | clarification_required | needs_user_choice | user_selected"),
    source: str = Query("", description="workflow (/api/patient-routing) | analyze (/api/analyze)"),
):
    histories = load_histories()
    needle = q.strip().lower()
    rows = [
        h for h in histories
        if (not decision or h.get("decision") == decision)
        and (not source or h.get("source") == source)
        and (not needle or needle in " ".join(str(h.get(k) or "") for k in
                                              ("text", "suggested_specialty", "request_id")).lower())
    ]
    stats = {
        "total": len(histories),
        "shown": min(len(rows), limit),
        "by_decision": {},
        "avg_total_ms": None,
    }
    for h in histories:
        key = h.get("decision") or "none"
        stats["by_decision"][key] = stats["by_decision"].get(key, 0) + 1
    times = [h["total_ms"] for h in histories if h.get("total_ms")]
    if times:
        stats["avg_total_ms"] = int(sum(times) / len(times))
    return {"stats": stats, "requests": rows[:limit]}


@router.get("/api/admin/requests/{request_id}")
def get_request(request_id: str):
    detail = request_detail(request_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"No request {request_id} in the trace log")
    return detail
