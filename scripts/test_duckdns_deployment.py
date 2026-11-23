"""Offline coverage of the deployment modes and their task/secret boundaries."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import sys
import unittest

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


if __name__ == "__main__":
    unittest.main()
