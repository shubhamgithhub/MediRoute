"""Offline coverage of the deployment modes and their task/secret boundaries."""
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import tempfile
import sys
import unittest
from unittest.mock import patch

from demo_session import release_candidates, resolve_release, stop_deadline

ROOT = Path(__file__).resolve().parents[1]
DIGEST = "@sha256:" + "a" * 64
ENV = {
    "TASK_CPU": "1024",
    "TASK_MEMORY": "4096",
    "TASK_EXECUTION_ROLE_ARN": "execution-role",
    "TASK_ROLE_ARN": "task-role",
    "BACKEND_IMAGE": "backend" + DIGEST,
    "FRONTEND_IMAGE": "frontend" + DIGEST,
    "CLOUDFLARED_IMAGE": "cloudflared" + DIGEST,
    "LOG_GROUP": "/ecs/mediroute-demo",
    "AWS_REGION": "ap-southeast-2",
    "OPENROUTER_API_KEY_PARAMETER_ARN": "openrouter-parameter",
}


def render(mode=None, label=None):
    env = {**os.environ, **ENV}
    for key, val in (("MEDIROUTE_ENDPOINT_MODE", mode), ("MEDIROUTE_DUCKDNS_LABEL", label)):
        if val is None:
            env.pop(key, None)
        else:
            env[key] = val
    return subprocess.run(
        [sys.executable, "scripts/render_ecs_task.py", "render"],
        cwd=ROOT, env=env, check=False, capture_output=True, text=True,
    )


class DuckDNSDeploymentTests(unittest.TestCase):
    def test_default_keeps_quick_tunnel_and_ignores_duckdns_label(self):
        default = render(label="mediroute-demo")
        self.assertEqual(default.returncode, 0, default.stderr)
        task = json.loads(default.stdout)
        api, frontend, tunnel = task["containerDefinitions"]
        self.assertEqual([api["name"], frontend["name"], tunnel["name"]], ["api", "frontend", "tunnel"])
        self.assertEqual(tunnel["command"], ["tunnel", "--url", "http://127.0.0.1:8080"])
        self.assertNotIn("portMappings", frontend)
        self.assertNotIn("secrets", frontend)
        self.assertEqual(json.loads(render("quick-tunnel").stdout), task)

    def test_duckdns_exposes_https_and_only_frontend_gets_dns_secrets(self):
        result = render("duckdns", "mediroute-demo")
        self.assertEqual(result.returncode, 0, result.stderr)
        task = json.loads(result.stdout)
        api, frontend = task["containerDefinitions"]
        self.assertEqual([api["name"], frontend["name"]], ["api", "frontend"])
        self.assertEqual(api, json.loads(render().stdout)["containerDefinitions"][0])
        self.assertEqual(frontend["portMappings"], [{"containerPort": 443, "protocol": "tcp"}])
        self.assertEqual(frontend["environment"], [{"name": "MEDIROUTE_DUCKDNS_LABEL", "value": "mediroute-demo"}])
        self.assertEqual(frontend["dependsOn"], [{"containerName": "api", "condition": "HEALTHY"}])
        policy = json.loads((ROOT / "infra/iam/ecs-duckdns-parameters-read.json").read_text())
        statement, = policy["Statement"]
        self.assertEqual(statement["Action"], "ssm:GetParameters")
        self.assertCountEqual([s["valueFrom"] for s in frontend["secrets"]], statement["Resource"])

    def test_bad_hostnames_and_modes_fail_without_task_json(self):
        for mode, label in [
            ("duckdns", None),
            ("duckdns", "mediroute.duckdns.org"),
            ("duckdns", "-mediroute"),
            ("duckdns", "a" * 64),
            ("duckdns", "x; listen 80;"),
            ("other", "mediroute"),
        ]:
            with self.subTest(mode=mode, label=label):
                result = render(mode, label)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")


class DeploymentRuntimeTests(unittest.TestCase):
    def test_manual_validation_respects_the_trusted_runtime(self):
        for trusted, scheduled in (("1440", "1440"), ("120", "120")):
            with self.subTest(trusted=trusted):
                result = subprocess.run(
                    ["bash", "scripts/deploy_ecs.sh", "validate"], cwd=ROOT,
                    capture_output=True, text=True, check=True,
                    env={**os.environ, "MEDIROUTE_TRUSTED_MAX_RUNTIME_MINUTES": trusted},
                )
                self.assertIn(f"scheduled stop after {scheduled} minutes", result.stdout)

    def test_policy_rejects_runtime_over_24_hours(self):
        source = (ROOT / "infra/deployment-control.yaml").read_text()
        with tempfile.TemporaryDirectory() as temp:
            policy = Path(temp) / "policy.yaml"
            policy.write_text(source.replace("max_runtime_minutes: 1440", "max_runtime_minutes: 1441"))
            result = subprocess.run(
                [sys.executable, "scripts/check_deployment_policy.py", str(policy),
                 "feature/aws_deployment", "true", "false"],
                cwd=ROOT, capture_output=True, text=True,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("max_runtime_minutes must be between 1 and 1440", result.stderr)


class DemoSessionTests(unittest.TestCase):
    def test_open_and_close_in_ist_through_final_demo_day(self):
        cases = {
            "2026-11-23T12:00:00+05:30": None,
            "2026-12-06T07:59:59+05:30": None,
            "2026-12-06T08:00:00+05:30": "2026-12-06T18:30:00+00:00",
            "2026-12-06T23:50:00+05:30": "2026-12-06T18:30:00+00:00",
            "2026-12-06T23:59:00+05:30": None,
            "2026-12-07T00:00:00+05:30": None,
            "2026-12-07T08:00:00+05:30": None,
            "2027-12-06T09:00:00+05:30": None,
        }
        for start, expected in cases.items():
            with self.subTest(start=start):
                deadline = stop_deadline(datetime.fromisoformat(start))
                self.assertEqual(deadline.isoformat() if deadline else None, expected)

    def test_shorter_trusted_cap_still_applies(self):
        started = datetime.fromisoformat("2026-12-06T08:00:00+05:30")
        self.assertEqual(stop_deadline(started, 120).isoformat(), "2026-12-06T04:30:00+00:00")

    def test_release_uses_newest_complete_active_immutable_pair(self):
        def image(tag, digest, hour, status="ACTIVE"):
            return {"imageTags": [tag], "imageDigest": "sha256:" + digest * 64,
                    "imagePushedAt": f"2026-12-01T{hour:02d}:00:00+00:00", "imageStatus": status}

        old, latest, partial, archived = ("sha-" + letter * 40 for letter in "abcd")
        frontend = [image(old, "a", 11), image(latest, "b", 13), image(archived, "d", 15)]
        backend = [image(old, "e", 11), image(latest, "f", 12), image(partial, "1", 14),
                   image(archived, "2", 15, "ARCHIVED"), image("latest", "3", 16)]
        pairs = release_candidates(backend, frontend)
        self.assertEqual([p["sha"] for p in pairs], ["b" * 40, "a" * 40])
        self.assertEqual(pairs[0]["backend"], "sha256:" + "f" * 64)
        self.assertEqual(pairs[0]["frontend"], "sha256:" + "b" * 64)


    def test_release_prefers_newest_complete_main_commit_over_late_older_build(self):
        main, prior, merged_feature = ("a" * 40, "b" * 40, "c" * 40)
        repo = "example/MediRoute"
        history = f"{main}\n{prior}\n"

        def read_json(*args):
            if args[0] == "aws":
                return {"imageDetails": []}
            sha = args[-1].split("head_sha=")[1].split("&")[0]
            return {"workflow_runs": [{"head_sha": sha, "event": "push",
                                      "head_branch": "main", "conclusion": "success",
                                      "head_repository": {"full_name": repo}}]}

        pairs = [{"sha": sha} for sha in (prior, merged_feature, main)]
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": repo, "GITHUB_SHA": main}), \
                patch("demo_session.release_candidates", return_value=pairs), \
                patch("demo_session.subprocess.check_output", return_value=history), \
                patch("demo_session.subprocess.run", return_value=subprocess.CompletedProcess([], 0)), \
                patch("demo_session.read_json", side_effect=read_json):
            self.assertEqual(resolve_release(None)["sha"], main)
            self.assertEqual(resolve_release(prior)["sha"], prior)


if __name__ == "__main__":
    unittest.main()
