#!/usr/bin/env python3
"""Fail-closed MediRoute auto-deployment policy evaluator.

Usage: python check_deployment_policy.py POLICY.yaml BRANCH CI_OK EMERGENCY_DISABLED
Where CI_OK and EMERGENCY_DISABLED are true|false strings.

This is only a policy gate, NOT a security boundary: IAM and trusted workflows
must independently protect AWS deployment privileges.
"""
import fnmatch
import json
import sys

try:
    import yaml
except ImportError as exc:
    raise SystemExit("Install reviewed PyYAML in CI before running this gate") from exc


def main():
    if len(sys.argv) != 5:
        raise SystemExit("usage: check_deployment_policy.py <yaml> <branch> <ci_ok> <emergency_disabled>")
    path, branch, ci, emergency = sys.argv[1:]
    if ci not in ("true", "false") or emergency not in ("true", "false"):
        raise SystemExit("ci_ok and emergency_disabled must be lowercase true|false")
    with open(path, encoding="utf-8") as handle:
        root = yaml.safe_load(handle)
    if not isinstance(root, dict) or not isinstance(root.get("deployment"), dict):
        raise SystemExit("Invalid config root")
    rule = root["deployment"]
    allowed_keys = {"auto_deploy", "allowed_branches", "environment", "max_runtime_minutes", "max_running_tasks", "on_existing_demo"}
    if set(rule) - allowed_keys:
        raise SystemExit("Unknown policy keys; fail closed")
    if type(rule.get("auto_deploy")) is not bool:
        raise SystemExit("auto_deploy must be a YAML boolean")
    branches = rule.get("allowed_branches")
    if not isinstance(branches, list) or not branches or not all(isinstance(x, str) and x for x in branches):
        raise SystemExit("allowed_branches must be nonempty list of strings")
    if rule.get("on_existing_demo") != "skip":
        raise SystemExit("Only skip is supported while capstone budget is constrained")
    if type(rule.get("max_running_tasks")) is not int or rule["max_running_tasks"] != 1:
        raise SystemExit("Exactly one task is supported")
    minutes = rule.get("max_runtime_minutes")
    if type(minutes) is not int or not 1 <= minutes <= 120:
        raise SystemExit("max_runtime_minutes must be between 1 and 120")
    approved = bool(rule["auto_deploy"] and ci == "true" and emergency == "false"
                    and any(fnmatch.fnmatchcase(branch, pattern) for pattern in branches))
    # fnmatch '*' can span '/': treat feature/** as an explicit exception to mimic expected prefix matching.
    print(json.dumps({"deploy_requested": approved, "branch": branch, "ci_ok": ci == "true",
                      "emergency_disabled": emergency == "true", "policy_enabled": rule["auto_deploy"]}))
    # Exit 0 for both allowed/skipped; use JSON output to decide next job. Invalid policy exits nonzero.


if __name__ == "__main__":
    main()
