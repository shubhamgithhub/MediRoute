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

    print(json.dumps(rendered, indent=2))

if __name__ == "__main__":
    main()
