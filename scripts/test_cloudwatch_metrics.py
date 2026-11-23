"""Offline telemetry contract, ASGI, provider and dashboard tests (stdlib only)."""
import asyncio
import concurrent.futures
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mediroute.backend import health_monitor
from mediroute.utils import cloudwatch_metrics as metrics
from mediroute.specialty_routing.step1.ollama_client import OpenRouterClient

spec = importlib.util.spec_from_file_location("dashboard", ROOT / "monitoring/build_dashboard.py")
dashboard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dashboard)

spec = importlib.util.spec_from_file_location("status_widget", ROOT / "monitoring/status_widget.py")
status_widget = importlib.util.module_from_spec(spec)
spec.loader.exec_module(status_widget)


def events(output):
    return [json.loads(line) for line in output.getvalue().splitlines()]


class MetricsTests(unittest.TestCase):
    def setUp(self):
        self.flag = patch.dict("os.environ", {"MEDIROUTE_METRICS_ENABLED": "true"})
        self.flag.start()
        self.addCleanup(self.flag.stop)

    def test_emf_shape_and_no_high_cardinality_fields(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            metrics.emit({"Queries": 1, "QueriesFailed": 0, "QueryTimeMs": 12.5})
        event = events(output)[0]
        self.assertEqual(set(event), {"_aws", "Environment", "Queries", "QueriesFailed", "QueryTimeMs"})
        directive = event["_aws"]["CloudWatchMetrics"][0]
        self.assertEqual(directive["Namespace"], "MediRoute/Demo")
        self.assertEqual(directive["Dimensions"], [["Environment"]])
        self.assertEqual(event["Environment"], "dev")
        self.assertIsInstance(event["_aws"]["Timestamp"], int)
        self.assertTrue(all(m["StorageResolution"] == 60 for m in directive["Metrics"]))

    def test_disabled_by_default_and_explicit_false(self):
        for flag in ("", "false", "1"):
            with patch.dict("os.environ", {"MEDIROUTE_METRICS_ENABLED": flag}), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                metrics.emit({"Queries": 1})
            self.assertEqual(output.getvalue(), "")

    def test_invalid_or_sensitive_fields_not_emitted(self):
        for values in ({}, {"patient": "private"}, {"Queries": 1, "request_id": "private"},
                       {"Queries": True}, {"Queries": -1}, {"QueryTimeMs": float("nan")},
                       {"LLMCostUSD": float("inf")}, {"LLMCostUSD": "0.1"}):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                metrics.emit(values)
            self.assertEqual(output.getvalue(), "")

    def test_parallel_output_is_valid_json_per_line(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(lambda _: metrics.record_llm_attempt({"cost": 0.01}, 10, False), range(40)))
        self.assertEqual(len(events(output)), 40)
        self.assertAlmostEqual(sum(e["LLMCostUSD"] for e in events(output)), 0.4)

    def test_unknown_cost_is_absent_not_zero(self):
        for value in (None, "unknown", -1, float("nan"), True):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                metrics.record_llm_attempt({"cost": value}, 10, False)
            event = events(output)[0]
            self.assertEqual(event["LLMCostMissing"], 1)
            self.assertNotIn("LLMCostUSD", event)

    def test_reported_zero_is_known(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            metrics.record_llm_attempt({"cost": 0}, 10, False)
        self.assertEqual(events(output)[0]["LLMCostUSD"], 0)
        self.assertEqual(events(output)[0]["LLMCostMissing"], 0)

    def test_output_failure_is_nonfatal(self):
        with patch.object(metrics.sys, "stdout") as output:
            output.write.side_effect = OSError("disk/pipe error")
            metrics.record_llm_attempt({"cost": 0.1}, 10, False)

    def test_observer_preserves_exceptions_and_counts_attempt(self):
        @metrics.observe_llm_call
        def failing():
            raise RuntimeError("private provider details")
        with contextlib.redirect_stdout(io.StringIO()) as output, self.assertRaises(RuntimeError):
            failing()
        self.assertEqual(events(output)[0]["LLMCostMissing"], 1)
        self.assertEqual(events(output)[0]["LLMCallsFailed"], 1)
        self.assertGreaterEqual(events(output)[0]["LLMCallTimeMs"], 0)
        self.assertNotIn("private", output.getvalue())

    def test_observer_preserves_result_when_metrics_break(self):
        @metrics.observe_llm_call
        def call():
            return {"usage": {"cost": 0.12}}
        with patch.object(metrics, "record_llm_attempt", side_effect=RuntimeError):
            self.assertEqual(call(), {"usage": {"cost": 0.12}})


class MiddlewareTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.flag = patch.dict("os.environ", {"MEDIROUTE_METRICS_ENABLED": "true"})
        self.flag.start()
        self.addCleanup(self.flag.stop)

    async def invoke(self, status=200, path="/api/patient-routing", method="POST",
                     error=False, incomplete=False, background_error=False, send_error=False, headers=()):
        sent = []
        async def app(scope, receive, send):
            if error:
                raise RuntimeError("private patient details")
            await send({"type": "http.response.start", "status": status, "headers": []})
            await send({"type": "http.response.body", "body": b"private", "more_body": True})
            if not incomplete:
                await send({"type": "http.response.body", "body": b"", "more_body": False})
            if background_error:
                raise RuntimeError("background failure")
        async def receive():
            raise AssertionError("metrics must not read request body")
        async def send(message):
            if send_error:
                raise OSError("client disconnected")
            sent.append(message)
        wrapped = metrics.QueryMetricsMiddleware(app)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            try:
                await wrapped({"type": "http", "method": method, "path": path,
                               "query_string": b"secret", "headers": headers}, receive, send)
            except (RuntimeError, OSError):
                if not (error or background_error or send_error):
                    raise
        self.assertNotIn("private", output.getvalue())
        self.assertNotIn("secret", output.getvalue())
        return events(output), sent

    async def test_success_counted_once_after_final_body(self):
        result, sent = await self.invoke()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["Queries"], 1)
        self.assertEqual(result[0]["QueriesFailed"], 0)
        self.assertEqual(result[0]["QueriesRejected"], 0)
        self.assertGreaterEqual(result[0]["QueryTimeMs"], 0)
        self.assertEqual(len(sent), 3)

    async def test_only_patient_routing_marked_retries_count(self):
        for headers, path, expected in (
            ([(b"x-mediroute-retry", b"1")], "/api/patient-routing", 1),
            ([(b"x-mediroute-retry", b"0")], "/api/patient-routing", 0),
            ([(b"x-mediroute-retry", b"1")], "/api/analyze", 0),
            ([], "/api/patient-routing", 0),
        ):
            result, _ = await self.invoke(headers=headers, path=path)
            self.assertEqual(result[0]["QueriesRetried"], expected)

    async def test_http_failures_and_rejections(self):
        for status, failed, rejected in [(500, 1, 0), (503, 1, 0), (400, 0, 1), (422, 0, 1)]:
            result, _ = await self.invoke(status=status)
            self.assertEqual(result[0]["QueriesFailed"], failed)
            self.assertEqual(result[0]["QueriesRejected"], rejected)

    async def test_exceptions_incomplete_and_disconnected(self):
        for options in ({"error": True}, {"incomplete": True}, {"send_error": True}):
            result, _ = await self.invoke(**options)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["QueriesFailed"], 1)

    async def test_post_response_error_not_double_counted(self):
        result, _ = await self.invoke(background_error=True)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["QueriesFailed"], 0)

    async def test_excluded_routes_and_options(self):
        for path, method in [("/api/health", "GET"), ("/api/admin/requests", "GET"),
                             ("/", "GET"), ("/api/auth/login", "POST"),
                             ("/api/patient-routing", "OPTIONS")]:
            result, _ = await self.invoke(path=path, method=method)
            self.assertEqual(result, [])

    async def test_all_recommendation_routes(self):
        for path in metrics.QUERY_PATHS:
            result, _ = await self.invoke(path=path)
            self.assertEqual(len(result), 1)

    async def test_cancellation_counted_and_propagated(self):
        async def cancelled(scope, receive, send):
            raise asyncio.CancelledError()
        with contextlib.redirect_stdout(io.StringIO()) as output, self.assertRaises(asyncio.CancelledError):
            await metrics.QueryMetricsMiddleware(cancelled)(
                {"type": "http", "method": "POST", "path": "/api/analyze"}, None, None)
        self.assertEqual(events(output)[0]["QueriesFailed"], 1)

    async def test_concurrent_requests_independent(self):
        async def app(scope, receive, send):
            await asyncio.sleep(0)
            await send({"type": "http.response.start", "status": scope["status"]})
            await send({"type": "http.response.body", "body": b""})
        async def send(message):
            pass
        wrapped = metrics.QueryMetricsMiddleware(app)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            await asyncio.gather(*[
                wrapped({"type": "http", "method": "POST", "path": "/api/analyze",
                         "status": status}, None, send) for status in [200, 500, 422]])
        self.assertEqual(sum(e["Queries"] for e in events(output)), 3)
        self.assertEqual(sum(e["QueriesFailed"] for e in events(output)), 1)
        self.assertEqual(sum(e["QueriesRejected"] for e in events(output)), 1)

    async def test_emit_failure_does_not_change_response(self):
        with patch.object(metrics, "emit", side_effect=RuntimeError("telemetry broke")):
            result, sent = await self.invoke()
        self.assertEqual(result, [])
        self.assertEqual(len(sent), 3)


class Stream:
    def __init__(self, content="{}", cost=0.02, include_cost=True):
        usage = {"cost": cost, "prompt_tokens": 120, "completion_tokens": 30} if include_cost else {}
        self.lines = [
            b'data: {"choices":[{"delta":{"content":' + json.dumps(content).encode() + b'}}]}\n',
            ("data: " + json.dumps({"usage": usage}) + "\n").encode(),
            ("data: " + json.dumps({"usage": usage}) + "\n").encode(),
            b"data: [DONE]\n",
        ]
    def __enter__(self):
        return iter(self.lines)
    def __exit__(self, *args):
        return False


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.flag = patch.dict("os.environ", {"MEDIROUTE_METRICS_ENABLED": "true"})
        self.flag.start()
        self.addCleanup(self.flag.stop)
        self.client = OpenRouterClient(api_key="synthetic-test-key", model="test/model")

    def test_real_stream_parser_counts_usage_once(self):
        with patch("urllib.request.urlopen", return_value=Stream()), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            result = self.client.generate_json("private patient text", {}, "test")
        self.assertTrue(result.ok)
        self.assertEqual(len(events(output)), 1)
        self.assertEqual(events(output)[0]["LLMCostUSD"], 0.02)
        self.assertEqual(events(output)[0]["LLMInputTokens"], 120)
        self.assertEqual(events(output)[0]["LLMOutputTokens"], 30)
        self.assertEqual(events(output)[0]["LLMCallsFailed"], 0)
        self.assertGreaterEqual(events(output)[0]["LLMCallTimeMs"], 0)
        self.assertNotIn("synthetic-test-key", output.getvalue())
        self.assertNotIn("private", output.getvalue())

    def test_invalid_model_json_still_records_spend(self):
        with patch("urllib.request.urlopen", return_value=Stream(content="invalid json")), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            result = self.client.generate_json("private", {}, "test")
        self.assertFalse(result.ok)
        self.assertEqual(events(output)[0]["LLMCostUSD"], 0.02)

    def test_missing_usage_not_reported_as_free(self):
        with patch("urllib.request.urlopen", return_value=Stream(include_cost=False)), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.client.generate_json("private", {}, "test")
        self.assertNotIn("LLMCostUSD", events(output)[0])
        self.assertNotIn("LLMInputTokens", events(output)[0])
        self.assertNotIn("LLMOutputTokens", events(output)[0])
        self.assertEqual(events(output)[0]["LLMCostMissing"], 1)

    def test_rate_limit_retry_is_two_attempts(self):
        error = urllib.error.HTTPError("https://example.invalid", 429, "limit",
                                       {"Retry-After": "1"}, io.BytesIO(b"limited"))
        with patch("urllib.request.urlopen", side_effect=[error, Stream()]), \
             patch("time.sleep"), contextlib.redirect_stdout(io.StringIO()) as output:
            result = self.client.generate_json("private", {}, "test")
        self.assertTrue(result.ok)
        self.assertEqual(sum(e["LLMCalls"] for e in events(output)), 2)
        self.assertEqual(sum(e["LLMCostMissing"] for e in events(output)), 1)
        self.assertAlmostEqual(sum(e.get("LLMCostUSD", 0) for e in events(output)), 0.02)

    def test_no_key_skips_network_and_emits_no_cost(self):
        client = OpenRouterClient(api_key="", model="test/model")
        with patch("urllib.request.urlopen") as request, contextlib.redirect_stdout(io.StringIO()) as output:
            result = client.generate_json("private", {}, "test")
        self.assertFalse(result.ok)
        request.assert_not_called()
        self.assertEqual(output.getvalue(), "")


class HealthTests(unittest.TestCase):
    healthy = (200, b'{"status":"healthy","service":"MediRoute API"}')
    page = (200, b'<body class="patient-page">')

    def check(self, direct, page, proxy):
        responses = {(8000, "/api/health"): direct, (8080, "/patient.html"): page,
                     (8080, "/api/health"): proxy}
        return health_monitor.check_health(8000, get=lambda port, path: responses[port, path])

    def test_combined_app_requires_direct_api_frontend_and_proxy(self):
        self.assertEqual(self.check(self.healthy, self.page, self.healthy),
                         {"ApiProbeSuccess": 1, "AppProbeSuccess": 1})
        self.assertEqual(self.check(self.healthy, (200, b"wrong page"), self.healthy),
                         {"ApiProbeSuccess": 1, "AppProbeSuccess": 0})
        self.assertEqual(self.check(self.healthy, self.page, (502, b"bad gateway")),
                         {"ApiProbeSuccess": 1, "AppProbeSuccess": 0})
        self.assertEqual(self.check((200, b"[]"), self.page, self.healthy),
                         {"ApiProbeSuccess": 0, "AppProbeSuccess": 0})

    def test_probe_exits_on_shutdown_without_recording_a_sample(self):
        with patch.object(health_monitor, "emit") as emit:
            stop = threading.Event()
            stop.set()
            health_monitor.monitor_health(stop)
        emit.assert_not_called()


class DashboardTests(unittest.TestCase):
    def test_fixed_metric_series_and_no_container_insights(self):
        body = dashboard.build()
        found = set()
        for widget in body["widgets"]:
            self.assertIn(widget["type"], {"text", "metric", "custom"})
            for item in widget["properties"].get("metrics", []):
                if isinstance(item[0], str):
                    self.assertEqual(item[0], "MediRoute/Demo")
                    self.assertEqual(item[2:4], ["Environment", "dev"])
                    found.add(item[1])
                else:
                    self.assertNotIn("FILL(", item[0]["expression"])
        self.assertEqual(found, set(metrics.UNITS))
        self.assertEqual(len(found), 14)
        self.assertNotIn("ECS/ContainerInsights", json.dumps(body))
        self.assertNotIn("AWS/Route53", json.dumps(body))

    def test_status_widget_uses_the_demo_function_and_refreshes(self):
        custom, = [w for w in dashboard.build()["widgets"] if w["type"] == "custom"]
        self.assertEqual(custom["properties"]["endpoint"],
                         "arn:aws:lambda:ap-southeast-2:299952487175:function:customWidgetMediRouteStatus")
        self.assertEqual(custom["properties"]["updateOn"],
                         {"refresh": True, "resize": False, "timeRange": False})

    def test_dashboard_layout_and_generated_file_match(self):
        body = dashboard.build()
        self.assertEqual(json.loads((ROOT/"monitoring/mediroute-dashboard.json").read_text()), body)
        occupied = set()
        for w in body["widgets"]:
            cells = {(x, y) for x in range(w["x"], w["x"] + w["width"])
                     for y in range(w["y"], w["y"] + w["height"])}
            self.assertFalse(cells & occupied)
            occupied |= cells
            self.assertLessEqual(w["x"] + w["width"], 24)

    def test_no_data_and_unknown_cost_are_not_zero_filled(self):
        expressions = [m[0]["expression"] for w in dashboard.build()["widgets"]
                       for m in w["properties"].get("metrics", []) if isinstance(m[0], dict)]
        self.assertIn("IF(q>0,100*f/q)", expressions)
        self.assertIn("IF((q>0) AND (calls>0) AND (missing==0) AND (samples==calls),cost/q)", expressions)

    def test_ecs_opt_in_and_workflow_ci_integration(self):
        template = json.loads((ROOT/"infra/ecs/task-definition.template.json").read_text())
        api = next(c for c in template["containerDefinitions"] if c["name"] == "api")
        self.assertIn({"name": "MEDIROUTE_METRICS_ENABLED", "value": "true"}, api["environment"])
        self.assertEqual(api["logConfiguration"]["logDriver"], "awslogs")
        main = (ROOT/"src/mediroute/backend/main.py").read_text()
        self.assertIn("app.add_middleware(QueryMetricsMiddleware)", main)
        self.assertIn("python scripts/test_cloudwatch_metrics.py",
                      (ROOT/".github/workflows/ci.yml").read_text())
        self.assertIn("auto_deploy: false", (ROOT/"infra/deployment-control.yaml").read_text())


class StatusWidgetTests(unittest.TestCase):
    @staticmethod
    def fake_fetch(method, path, _limit):
        if method == "OPTIONS":
            return (404 if path == "/api/auth/signup" else 405), b""
        if method != "GET":
            raise AssertionError(f"Unexpected live method: {method}")
        if path == "/api/health":
            return 200, b'{"status":"healthy","service":"MediRoute API"}'
        if path == "/patient.html":
            return 200, b'<body class="patient-page">'
        return next((expected, b"") for url, expected, _ in status_widget.DIRECT.values() if url == path)

    def test_checks_are_read_only_with_expected_auth_and_validation_statuses(self):
        app, routes = status_widget.snapshot(self.fake_fetch)
        self.assertTrue(app)
        self.assertEqual(len(routes), 22)
        self.assertEqual(sum(up for up, _ in routes.values()), 21)
        self.assertTrue(routes[("GET", "/api/auth/me")][0])
        self.assertTrue(routes[("GET", "/api/hospitals/keyword-search")][0])
        self.assertFalse(routes[("POST", "/api/auth/signup")][0])
        html = status_widget.render(app, routes, "2026-11-23 09:00:00 UTC")
        self.assertIn("21/22 UP", html)
        self.assertIn("App · latest check", html)
        self.assertIn('background-color:#166534', html)
        self.assertIn('background-color:#991b1b', html)
        self.assertEqual(html.count(">DOWN</span>"), 1)

    def test_unreachable_app_and_api_are_down(self):
        app, routes = status_widget.snapshot(lambda *_: (0, b""))
        self.assertFalse(app)
        self.assertFalse(any(up for up, _ in routes.values()))
        html = status_widget.render(app, routes, "2026-11-23 09:00:00 UTC")
        self.assertEqual(html.count(">DOWN</span>"), 23)

    def test_unexpected_patient_html_marks_only_the_app_down(self):
        def wrong_page(method, path, limit):
            if path == "/patient.html":
                return 200, b"An unexpected page"
            return self.fake_fetch(method, path, limit)

        app, routes = status_widget.snapshot(wrong_page)
        self.assertFalse(app)
        self.assertTrue(routes[("GET", "/api/health")][0])


if __name__ == "__main__":
    unittest.main()
