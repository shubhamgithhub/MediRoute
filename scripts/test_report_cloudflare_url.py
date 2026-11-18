"""Offline deployment reporting checks; stdlib only, no credentials or AWS calls."""
import argparse
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "report_cloudflare_url", Path(__file__).with_name("report_cloudflare_url.py"))
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)
TASK = "arn:aws:ecs:ap-southeast-2:299952487175:task/mediroute-demo/" + "a" * 32
URL = "https://demo-test.trycloudflare.com"
ARGS = ["--task-arn", TASK, "--schedule-name", "mediroute-stop-20261119000000-1234abcd",
        "--stop-time-utc", "2026-11-19T02:00:00", "--branch", "feature/aws_deployment",
        "--commit", "b" * 40]


class Clock:
    now = 0
    def __call__(self):
        return self.now
    def sleep(self, seconds):
        self.now += seconds


class ReportingTests(unittest.TestCase):
    def discover(self, results):
        clock = Clock()
        calls = []
        def read(arguments, timeout=12):
            calls.append(arguments)
            result = results[min(len(calls) - 1, len(results) - 1)]
            if isinstance(result, Exception):
                raise result
            return result
        value = report.discover_url(TASK, read=read, sleep=clock.sleep, clock=clock,
                                    budget=30, interval=10)
        return value, calls, clock.now

    def test_immediate_url_and_exact_task_log_scope(self):
        (url, note), calls, _ = self.discover([["private text " + URL]])
        self.assertEqual((url, note), (URL, ""))
        self.assertEqual(len(calls), 1)
        self.assertIn("tunnel/tunnel/" + "a" * 32, calls[0])
        self.assertIn("/ecs/mediroute-demo", calls[0])

    def test_delayed_logs_and_latest_url(self):
        (url, _), calls, _ = self.discover([[], [], [
            "https://old-url.trycloudflare.com", URL]])
        self.assertEqual(url, URL)
        self.assertEqual(len(calls), 3)

    def test_missing_logs_have_bounded_wait(self):
        (url, note), calls, elapsed = self.discover([[]])
        self.assertEqual(url, "")
        self.assertIn("deadline", note)
        self.assertEqual((len(calls), elapsed), (3, 30))

    def test_access_denied_stops_retries(self):
        (url, note), calls, _ = self.discover([report.ReadError("AWS read permission denied")])
        self.assertEqual(url, "")
        self.assertIn("permission", note)
        self.assertEqual(len(calls), 1)

    def test_transient_failure_recovers(self):
        (url, _), calls, _ = self.discover([report.ReadError("AWS read failed"), [URL]])
        self.assertEqual(url, URL)
        self.assertEqual(len(calls), 2)

    def test_malformed_and_persistent_errors_are_nonfatal(self):
        for value in [None, {}, [None], report.ReadError("AWS returned invalid JSON"),
                      report.ReadError("AWS read timed out")]:
            with self.subTest(value=value):
                (url, note), calls, _ = self.discover([value])
                self.assertEqual(url, "")
                self.assertTrue(note)
                self.assertEqual(len(calls), 3)

    def test_hostname_suffix_is_not_accepted(self):
        (url, _), _, _ = self.discover([[URL + ".evil.example"]])
        self.assertEqual(url, "")

    def test_status_comes_from_exact_task(self):
        def read(arguments, timeout=12):
            self.assertEqual(arguments, ["ecs", "describe-tasks", "--cluster",
                                         "mediroute-demo", "--tasks", TASK])
            return {"tasks": [{"taskArn": TASK, "lastStatus": "RUNNING", "healthStatus": "HEALTHY"}]}
        self.assertEqual(report.task_status(TASK, read), ("RUNNING", "HEALTHY", ""))

    def test_status_errors_never_claim_running(self):
        for response in [{}, {"failures": [{"reason": "MISSING"}]},
                         {"tasks": [{"taskArn": "other", "lastStatus": "RUNNING"}]}, None]:
            with self.subTest(response=response):
                status, health, note = report.task_status(TASK, lambda *a, **kw: response)
                self.assertEqual((status, health), ("UNKNOWN", "UNKNOWN"))
                self.assertTrue(note)

    def test_stopped_task_url_is_historical(self):
        text = report.summary(report.parse_args(ARGS), URL, "", "STOPPED", "UNKNOWN", "")
        self.assertIn("Historical tunnel URL", text)
        self.assertIn("Task warning", text)
        self.assertNotIn("Deployment Successful", text)

    def test_cli_writes_summary_and_outputs_without_raw_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(path/"summary"),
                                         "GITHUB_OUTPUT": str(path/"output")}), \
                 patch("sys.argv", ["report", *ARGS]), \
                 patch.object(report, "discover_url", return_value=(URL, "")), \
                 patch.object(report, "task_status", return_value=("RUNNING", "HEALTHY", "")), \
                 contextlib.redirect_stdout(io.StringIO()):
                report.main()
            text = (path/"summary").read_text()
            self.assertIn("b" * 40, text)
            self.assertIn("feature/aws_deployment", text)
            self.assertIn("2026-11-19T02:00:00 UTC", text)
            self.assertIn("does not verify", text)
            self.assertEqual((path/"output").read_text(),
                             f"cloudflare_url={URL}\necs_status=RUNNING\n")

    def test_cli_reporting_failure_writes_warning_summary(self):
        with patch("sys.argv", ["report", *ARGS]), \
             patch.object(report, "discover_url", return_value=("", "AWS read permission denied")), \
             patch.object(report, "task_status", return_value=("UNKNOWN", "UNKNOWN", "AWS read failed")), \
             patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": "", "GITHUB_OUTPUT": ""}), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            report.main()
        self.assertIn("::warning::", output.getvalue())
        self.assertIn("URL unavailable", output.getvalue())

    def test_invalid_metadata_rejected_before_aws(self):
        invalid = ARGS.copy()
        invalid[-1] = "not-a-commit"
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            report.parse_args(invalid)

    def test_aws_timeouts_retries_and_error_redaction(self):
        with patch.object(report.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 1, "", "AccessDenied secret")) as run:
            with self.assertRaisesRegex(report.ReadError, "^AWS read permission denied$"):
                report.aws_json(["logs", "filter-log-events"])
            kwargs = run.call_args.kwargs
            self.assertEqual(kwargs["timeout"], 12)
            self.assertEqual(kwargs["env"]["AWS_MAX_ATTEMPTS"], "1")
            self.assertIn("--region", run.call_args.args[0])
        with patch.object(report.subprocess, "run", side_effect=subprocess.TimeoutExpired("aws", 12)):
            with self.assertRaisesRegex(report.ReadError, "timed out"):
                report.aws_json(["ecs", "describe-tasks"])


if __name__ == "__main__":
    unittest.main()
