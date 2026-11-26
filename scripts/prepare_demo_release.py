"""Register the latest published main release for the AWS morning controller.

This writes only a task definition and non-secret SSM release metadata; no task starts.
Run only after the exact main commit passed CI and both images were published.
"""
import json
import os
import re
import subprocess

from demo_session import resolve_release
from demo_controller import RELEASE_PARAMETER, DEFINITION_PREFIX


def run(*args):
    return subprocess.check_output(args, text=True, timeout=90).strip()


def main():
    sha = os.environ["SOURCE_SHA"]
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise SystemExit("Invalid source SHA")
    repo = os.environ["GITHUB_REPOSITORY"]
    current = json.loads(run("gh", "api", f"repos/{repo}/commits/main"))["sha"]
    if current != sha:
        print("SKIP: A newer main commit exists; retain the last prepared release")
        return
    if run("git", "rev-parse", "HEAD") != sha:
        raise SystemExit("The checkout must match the published release")
    os.environ["GITHUB_SHA"] = sha
    pair = resolve_release(sha)
    registry = "299952487175.dkr.ecr.ap-southeast-2.amazonaws.com"
    os.environ.update(
        MEDIROUTE_ENDPOINT_MODE="duckdns",
        BACKEND_IMAGE=f"{registry}/mediroute-backend@{pair['backend']}",
        FRONTEND_IMAGE=f"{registry}/mediroute-frontend@{pair['frontend']}",
    )
    output = run("bash", "scripts/deploy_ecs.sh", "register")
    match = re.search(r"PASS: Registered (" + re.escape(DEFINITION_PREFIX) + r"[0-9]+)", output)
    if not match:
        raise SystemExit("Task definition registration did not return its ARN")
    pair["task_definition"] = match.group(1)
    # Publication jobs use one shared concurrency group; old builds cannot roll back the pointer.
    if json.loads(run("gh", "api", f"repos/{repo}/commits/main"))["sha"] != sha:
        print("SKIP: Main advanced during registration; retain the last prepared release")
        return
    run("aws", "ssm", "put-parameter", "--name", RELEASE_PARAMETER, "--type", "String",
        "--tier", "Standard", "--overwrite", "--value", json.dumps(pair))
    print("Prepared approved main release: " + json.dumps(pair))


if __name__ == "__main__":
    main()
