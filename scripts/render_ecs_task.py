#!/usr/bin/env python3
"""Validate or render the MediRoute ECS task definition."""

import json
import os
import re
import sys
from pathlib import Path

TEMPLATE = Path("infra/ecs/task-definition.template.json")

EXPECTED = {
    "TASK_CPU",
    "TASK_MEMORY",
    "TASK_EXECUTION_ROLE_ARN",
    "TASK_ROLE_ARN",
    "BACKEND_IMAGE",
    "FRONTEND_IMAGE",
    "CLOUDFLARED_IMAGE",
    "LOG_GROUP",
    "AWS_REGION",
    "OPENROUTER_API_KEY_PARAMETER_ARN",
}

DUCKDNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
DUCKDNS_PARAMETER_PREFIX = (
    "arn:aws:ssm:ap-southeast-2:299952487175:parameter/mediroute/dev/duckdns"
)


def configure_duckdns(task, label):
    if not DUCKDNS_LABEL.fullmatch(label):
        raise SystemExit("MEDIROUTE_DUCKDNS_LABEL must be one lowercase DuckDNS label")
    frontend = next(c for c in task["containerDefinitions"] if c["name"] == "frontend")
    frontend.setdefault("environment", []).append({"name": "MEDIROUTE_DUCKDNS_LABEL", "value": label})
    frontend["portMappings"] = [{"containerPort": 443, "protocol": "tcp"}]
    frontend["secrets"] = [
        {"name": name, "valueFrom": f"{DUCKDNS_PARAMETER_PREFIX}/{parameter}"}
        for name, parameter in [
            ("MEDIROUTE_DUCKDNS_TOKEN", "token"),
            ("MEDIROUTE_DUCKDNS_CERT", "fullchain"),
            ("MEDIROUTE_DUCKDNS_KEY", "privkey"),
        ]
    ]
    task["containerDefinitions"] = [c for c in task["containerDefinitions"] if c["name"] != "tunnel"]


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("validate", "render"):
        raise SystemExit("Usage: render_ecs_task.py validate|render")

    source = TEMPLATE.read_text()
    found = set(re.findall(r"\$\{([A-Z_]+)\}", source))

    if found != EXPECTED:
        raise SystemExit(
            f"Invalid placeholders. Missing: {EXPECTED - found}; "
            f"Unexpected: {found - EXPECTED}"
        )

    template = json.loads(source)
    assert template["family"] == "mediroute-demo"
    assert template["requiresCompatibilities"] == ["FARGATE"]

    containers = {
        c["name"]: c for c in template["containerDefinitions"]
    }
    assert set(containers) == {"api", "frontend", "tunnel"}

    api = containers["api"]
    secrets = {s["name"]: s["valueFrom"] for s in api["secrets"]}
    assert secrets["OPENROUTER_API_KEY"] == (
        "${OPENROUTER_API_KEY_PARAMETER_ARN}"
    )

    if sys.argv[1] == "validate":
        print("PASS: ECS template structure and placeholders valid")
        return

    values = {}
    for name in EXPECTED:
        value = os.getenv(name)
        if not value:
            raise SystemExit(f"Missing environment variable: {name}")
        values[name] = value

    if values["TASK_CPU"] != "1024":
        raise SystemExit("Only 1024 CPU units permitted")
    if values["TASK_MEMORY"] != "4096":
        raise SystemExit("Only 4096 MiB memory permitted")

    for name in ("BACKEND_IMAGE", "FRONTEND_IMAGE", "CLOUDFLARED_IMAGE"):
        if not re.search(r"@sha256:[0-9a-f]{64}$", values[name]):
            raise SystemExit(f"{name} must use an immutable image digest")

    for name, value in values.items():
        source = source.replace("${" + name + "}", value)

    rendered = json.loads(source)
    if "${" in json.dumps(rendered):
        raise SystemExit("Unresolved task-definition placeholder")

    mode = os.getenv("MEDIROUTE_ENDPOINT_MODE", "quick-tunnel")
    if mode == "duckdns":
        configure_duckdns(rendered, os.getenv("MEDIROUTE_DUCKDNS_LABEL", ""))
    elif mode != "quick-tunnel":
        raise SystemExit("Invalid MEDIROUTE_ENDPOINT_MODE")
    print(json.dumps(rendered, indent=2))

if __name__ == "__main__":
    main()
