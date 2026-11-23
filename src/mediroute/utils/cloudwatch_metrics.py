"""Low-cardinality CloudWatch EMF telemetry. No AWS SDK or request contents."""
from __future__ import annotations

from functools import wraps
import json
import math
import os
import sys
import threading
import time

NAMESPACE = "MediRoute/Demo"
ENVIRONMENT = "dev"
QUERY_PATHS = frozenset({
    "/api/patient-routing", "/api/analyze", "/api/hospitals/recommend",
    "/api/hospitals/semantic-recommendations",
})
UNITS = {
    "Queries": "Count", "QueriesFailed": "Count", "QueriesRejected": "Count",
    "QueryTimeMs": "Milliseconds", "LLMCalls": "Count", "LLMCostMissing": "Count",
    "LLMCostUSD": "None",
    "QueriesRetried": "Count",
    "LLMCallTimeMs": "Milliseconds",
    "LLMCallsFailed": "Count",
    "LLMInputTokens": "Count",
    "LLMOutputTokens": "Count",
    "ApiProbeSuccess": "Count",
    "AppProbeSuccess": "Count",
}
_OUTPUT_LOCK = threading.Lock()


def enabled():
    # Off for local development; explicitly enabled in the ECS api container.
    return os.getenv("MEDIROUTE_METRICS_ENABLED", "false").strip().lower() == "true"


def emit(values):
    """One plain JSON line, without the application's text logger prefix.

    Failures are deliberately swallowed: telemetry must not fail an API request.
    Only allowlisted numeric measurements and a fixed dimension can leave here.
    """
    if not enabled():
        return
    try:
        if not values or not set(values) <= set(UNITS):
            return
        if any(type(value) not in (int, float) or not math.isfinite(value) or value < 0
               for value in values.values()):
            return
        event = {
            "_aws": {
                "Timestamp": int(time.time() * 1000),
                "CloudWatchMetrics": [{
                    "Namespace": NAMESPACE,
                    "Dimensions": [["Environment"]],
                    "Metrics": [{"Name": name, "Unit": UNITS[name], "StorageResolution": 60}
                                for name in values],
                }],
            },
            "Environment": ENVIRONMENT,
            **values,
        }
        line = json.dumps(event, separators=(",", ":"), allow_nan=False) + "\n"
        with _OUTPUT_LOCK:
            sys.stdout.write(line)
            sys.stdout.flush()
    except Exception:
        pass


def record_llm_attempt(usage, elapsed_ms, failed):
    cost = usage.get("cost")
    known = type(cost) in (int, float) and math.isfinite(cost) and cost >= 0
    values = {
        "LLMCalls": 1,
        "LLMCallTimeMs": elapsed_ms,
        "LLMCallsFailed": int(failed),
        "LLMCostMissing": int(not known),
    }
    if known:
        values["LLMCostUSD"] = cost
    for metric, field in (("LLMInputTokens", "prompt_tokens"),
                          ("LLMOutputTokens", "completion_tokens")):
        count = usage.get(field)
        if type(count) is int and count >= 0:
            values[metric] = count
    emit(values)


def observe_llm_call(function):
    """Observe each actual OpenRouter stream attempt, not each usage chunk.

    Failed calls may still be billed. Unknown cost is missing, never assumed zero.
    Provider retries/fallbacks each pass through this wrapper independently.
    """
    @wraps(function)
    def observed(*args, **kwargs):
        if not enabled():
            return function(*args, **kwargs)
        start = time.perf_counter()
        failed = True
        usage = {}
        try:
            result = function(*args, **kwargs)
            failed = False
            if isinstance(result, dict) and isinstance(result.get("usage"), dict):
                usage = result["usage"]
            return result
        finally:
            # Even a telemetry programming/output error must preserve provider behavior.
            try:
                record_llm_attempt(usage, (time.perf_counter() - start) * 1000, failed)
            except Exception:
                pass
    return observed


class QueryMetricsMiddleware:
    """Measure one HTTP recommendation attempt through its final response body.

    5xx/exceptions/incomplete responses fail; 4xx are rejected separately.
    Clarifications and no-match responses are successful HTTP requests.
    Health checks, static pages, admin, accounts and OPTIONS are excluded.
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (not enabled() or scope["type"] != "http" or scope.get("method") != "POST"
                or scope.get("path") not in QUERY_PATHS):
            return await self.app(scope, receive, send)

        start = time.perf_counter()
        status = 500
        recorded = False
        retried = scope.get("path") == "/api/patient-routing" and any(
            name.lower() == b"x-mediroute-retry" and value == b"1"
            for name, value in scope.get("headers", ())
        )

        def finish(failed=False):
            nonlocal recorded
            if recorded:
                return
            recorded = True
            try:
                emit({
                    "Queries": 1,
                    "QueriesFailed": int(failed or status >= 500),
                    "QueriesRejected": int(not failed and 400 <= status < 500),
                    "QueriesRetried": int(retried),
                    "QueryTimeMs": max(0.0, (time.perf_counter() - start) * 1000),
                })
            except Exception:
                pass

        async def measured_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                finish()

        try:
            await self.app(scope, receive, measured_send)
        finally:
            # Also covers uncaught exceptions, cancellation and an incomplete response.
            # A post-response background error does not rewrite an already served result.
            if not recorded:
                finish(failed=True)
