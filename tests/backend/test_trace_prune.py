"""prune_trace keeps the newest N request histories (with their workflow lines) and drops the rest."""
import json

from mediroute.backend.admin.trace_reader import load_histories, prune_trace


def _write(path, events):
    path.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")


def _request(i):
    rid, wid, ts = f"s{i}", f"w{i}", f"2026-11-12T10:00:{i:02d}.000+00:00"
    return [
        {"ts": ts, "request_id": wid, "stage": "workflow:start"},
        {"ts": ts, "request_id": wid, "stage": "workflow:step1_route", "step1_request_id": rid},
        {"ts": ts, "request_id": rid, "stage": "input", "patient_text": {"text": f"request {i}"}},
        {"ts": ts, "request_id": rid, "stage": "response"},
    ]


def test_keeps_newest_requests_and_their_workflow_lines(tmp_path):
    trace = tmp_path / "trace.jsonl"
    _write(trace, [e for i in range(5) for e in _request(i)] + [{"ts": "x", "stage": "orphan"}])
    result = prune_trace(keep=2, path=trace)
    assert result == {"kept_requests": 2, "removed_lines": 13}
    ids = {json.loads(line)["request_id"] for line in trace.read_text(encoding="utf-8").splitlines()}
    assert ids == {"s3", "w3", "s4", "w4"}
    assert [h["request_id"] for h in load_histories(trace)] == ["s4", "s3"]


def test_nothing_removed_when_under_the_limit(tmp_path):
    trace = tmp_path / "trace.jsonl"
    _write(trace, _request(0))
    assert prune_trace(keep=100, path=trace) == {"kept_requests": 1, "removed_lines": 0}
    assert len(trace.read_text(encoding="utf-8").splitlines()) == 4
