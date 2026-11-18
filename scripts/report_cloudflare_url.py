#!/usr/bin/env python3
"""Report an existing MediRoute deployment; never launch or stop AWS resources."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import time

REGION = "ap-southeast-2"
CLUSTER = "mediroute-demo"
LOG_GROUP = "/ecs/mediroute-demo"
URL_PATTERN = re.compile(
    r"https://[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?\.trycloudflare\.com"
    r"(?![a-zA-Z0-9._-])"
)


class ReadError(Exception):
    pass


def aws_json(arguments, timeout=12):
    """Bound each read, disable CLI retries, and never expose raw AWS/log output."""
    env = dict(os.environ, AWS_MAX_ATTEMPTS="1", AWS_RETRY_MODE="standard", AWS_PAGER="")
    try:
        result = subprocess.run(
            ["aws", *arguments, "--region", REGION, "--output", "json",
             "--cli-connect-timeout", "4", "--cli-read-timeout", "5"],
            capture_output=True, text=True, timeout=timeout, env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise ReadError("AWS read timed out") from exc
    except OSError as exc:
        raise ReadError("AWS CLI could not be executed") from exc
    if result.returncode:
        if "AccessDenied" in result.stderr or "Unauthorized" in result.stderr:
            raise ReadError("AWS read permission denied")
        raise ReadError("AWS read failed")
    try:
        return json.loads(result.stdout)
    except ValueError as exc:
        raise ReadError("AWS returned invalid JSON") from exc


def discover_url(task_arn, read=aws_json, sleep=time.sleep, clock=time.monotonic,
                 budget=150, interval=10):
    deadline = clock() + budget
    note = "No tunnel URL appeared before the reporting deadline"
    while clock() < deadline:
        try:
            messages = read([
                "logs", "filter-log-events", "--log-group-name", LOG_GROUP,
                "--log-stream-name-prefix", "tunnel/tunnel/" + task_arn.rsplit("/", 1)[1],
                "--query", "events[].message",
            ], timeout=max(0.1, min(12, deadline - clock())))
            if not isinstance(messages, list) or not all(isinstance(m, str) for m in messages):
                raise ReadError("Unexpected CloudWatch response")
            # Prefer the latest URL if cloudflared has emitted more than one.
            for message in reversed(messages):
                matches = URL_PATTERN.findall(message)
                if matches:
                    return matches[-1], ""
            note = "No tunnel URL appeared before the reporting deadline"
        except ReadError as exc:
            note = str(exc)
            if note in ("AWS read permission denied", "AWS CLI could not be executed"):
                break
        remaining = deadline - clock()
        if remaining <= 0:
            break
        sleep(min(interval, remaining))
    return "", note


def task_status(task_arn, read=aws_json):
    try:
        response = read(["ecs", "describe-tasks", "--cluster", CLUSTER, "--tasks", task_arn])
        tasks = response.get("tasks", [])
        if response.get("failures") or len(tasks) != 1 or tasks[0].get("taskArn") != task_arn:
            raise ReadError("Task status could not be verified")
        task = tasks[0]
        status = task.get("lastStatus", "UNKNOWN")
        health = task.get("healthStatus", "UNKNOWN")
        allowed = {"PROVISIONING", "PENDING", "ACTIVATING", "RUNNING", "DEACTIVATING",
                   "STOPPING", "DEPROVISIONING", "STOPPED", "DELETED", "UNKNOWN"}
        if status not in allowed or health not in {"HEALTHY", "UNHEALTHY", "UNKNOWN"}:
            raise ReadError("Unexpected ECS status response")
        return status, health, ""
    except (ReadError, AttributeError, TypeError, KeyError, IndexError) as exc:
        note = str(exc) if isinstance(exc, ReadError) else "Unexpected ECS status response"
        return "UNKNOWN", "UNKNOWN", note


def summary(args, url, url_note, status, health, status_note):
    lines = [
        "### MediRoute deployment report", "",
        "- Guarded launch and automatic-stop schedule verification completed.",
        f"- Branch: `{args.branch}`",
        f"- Commit: `{args.commit}`",
        f"- ECS task ARN: `{args.task_arn}`",
        f"- ECS status (observed): **{status}**",
        f"- ECS health status (observed): `{health}`",
        f"- Automatic stop schedule: `{args.schedule_name}`",
        f"- Stop time UTC: `{args.stop_time_utc} UTC`", "",
    ]
    if url:
        label = "Historical tunnel URL (task is stopping/stopped)" if status in {
            "STOPPED", "STOPPING", "DEACTIVATING", "DEPROVISIONING", "DELETED"
        } else "Cloudflare HTTPS URL (from task logs)"
        lines += [f"**{label}:** {url}", ""]
    else:
        lines += [f"**Cloudflare HTTPS URL unavailable:** {url_note}.",
                  "This reporting result does not reverse the completed launch or stop schedule.", ""]
    if status_note:
        lines += [f"**Status warning:** {status_note}.", ""]
    if status in {"STOPPED", "STOPPING", "DEACTIVATING", "DEPROVISIONING", "DELETED"} or health == "UNHEALTHY":
        lines += ["**Task warning:** inspect ECS/container health before using this deployment.", ""]
    lines += [
        "A logged URL or RUNNING task does not verify end-to-end application readiness.",
        "The URL is temporary. Use synthetic patient information only.",
        f"Log fallback: `{LOG_GROUP}`, stream `tunnel/tunnel/{args.task_arn.rsplit('/', 1)[1]}`.",
        "",
    ]
    return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("task-arn", "schedule-name", "stop-time-utc", "branch", "commit"):
        parser.add_argument("--" + flag, required=True)
    args = parser.parse_args(argv)
    patterns = {
        "task_arn": r"arn:aws:ecs:ap-southeast-2:299952487175:task/mediroute-demo/[a-f0-9]{32}",
        "schedule_name": r"mediroute-stop-[0-9]{14}-[a-f0-9]{8}",
        "commit": r"[a-f0-9]{40}",
        "branch": r"(?:main|feature/aws_deployment)",
        "stop_time_utc": r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}",
    }
    for field, pattern in patterns.items():
        if not re.fullmatch(pattern, getattr(args, field)):
            parser.error("Invalid " + field)
    try:
        dt.datetime.strptime(args.stop_time_utc, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        parser.error("Invalid stop_time_utc date")
    return args


def main():
    args = parse_args()
    url, url_note = discover_url(args.task_arn)
    status, health, status_note = task_status(args.task_arn)
    report = summary(args, url, url_note, status, health, status_note)
    print(report)
    if not url or status_note or status != "RUNNING" or health == "UNHEALTHY":
        print("::warning::Deployment reporting needs attention; see the job summary.")
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as handle:
            handle.write(report)
    if os.getenv("GITHUB_OUTPUT"):
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as handle:
            handle.write(f"cloudflare_url={url}\necs_status={status}\n")


if __name__ == "__main__":
    main()
