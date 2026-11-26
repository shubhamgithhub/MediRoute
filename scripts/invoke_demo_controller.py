"""Invoke the shared demo controller and export its non-secret deployment results."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    operation = sys.argv[1]
    payload = {"operation": operation,
               "request_id": "github-" + os.environ["GITHUB_RUN_ID"] + "-" +
                             os.environ.get("GITHUB_RUN_ATTEMPT", "1")}
    if operation == "start" and os.environ.get("OPERATION") in {"publish-and-start", "deploy"}:
        payload["required_sha"] = os.environ["GITHUB_SHA"]
    with tempfile.TemporaryDirectory() as folder:
        destination = str(Path(folder) / "result.json")
        metadata = json.loads(subprocess.check_output([
            "aws", "lambda", "invoke", "--function-name", "mediroute-demo-control",
            "--cli-binary-format", "raw-in-base64-out", "--payload", json.dumps(payload),
            destination], text=True, timeout=180))
        result = json.loads(Path(destination).read_text())
    if metadata.get("FunctionError"):
        raise SystemExit("Demo controller failed: " + json.dumps(result))
    if result["status"] == "skipped":
        raise SystemExit("Demo controller refused launch: " + result["reason"])
    print(json.dumps(result, indent=2))
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            for key in ("task_arn", "source_sha", "schedule_name", "stop_time_utc"):
                if result.get(key):
                    print(f"{key}={result[key]}", file=output)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as output:
            print("### AWS demo controller\n\n```json\n" + json.dumps(result, indent=2) +
                  "\n```", file=output)
    if operation == "stop" and result.get("tasks"):
        subprocess.run(["aws", "ecs", "wait", "tasks-stopped", "--cluster", "mediroute-demo",
                        "--tasks", *result["tasks"]], check=True, timeout=180)


if __name__ == "__main__":
    main()
