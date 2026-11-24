"""Resolve the academic demo cutoff and a deployable immutable image pair."""

import argparse
from datetime import date, datetime, time, timedelta, timezone
import json
import os
import re
import subprocess
import sys
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")
FIRST_DAY = date(2026, 11, 24)
LAST_DAY = date(2026, 12, 6)
START = time(8)
MINIMUM_LEAD = timedelta(minutes=2)
COMPONENTS = ("backend", "frontend")
RELEASE_TAG = re.compile(r"sha-([0-9a-f]{40})")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


def stop_deadline(now, max_minutes=1440):
    local = now.astimezone(IST)
    if not FIRST_DAY <= local.date() <= LAST_DAY or local.time() < START:
        return None
    midnight = datetime.combine(local.date() + timedelta(days=1), time.min, tzinfo=IST)
    deadline = min(midnight, local + timedelta(minutes=max_minutes))
    return deadline.astimezone(timezone.utc) if deadline - local >= MINIMUM_LEAD else None


def release_candidates(backend, frontend):
    tagged = {}
    for component, images in zip(COMPONENTS, (backend, frontend)):
        releases = {}
        for image in images:
            digest = image.get("imageDigest", "")
            if image.get("imageStatus", "ACTIVE") != "ACTIVE" or not DIGEST.fullmatch(digest):
                continue
            for tag in image.get("imageTags", ()):
                match = RELEASE_TAG.fullmatch(tag)
                if match:
                    pushed = datetime.fromisoformat(image["imagePushedAt"])
                    releases[match[1]] = pushed, digest
        tagged[component] = releases
    back, front = (tagged[component] for component in COMPONENTS)
    pairs = [(max(back[sha][0], front[sha][0]), sha, back[sha][1], front[sha][1])
             for sha in back.keys() & front.keys()]
    return [{"sha": sha, "backend": back_digest, "frontend": front_digest}
            for _, sha, back_digest, front_digest in sorted(pairs, reverse=True)]


def read_json(*args):
    return json.loads(subprocess.check_output(args, text=True, timeout=30))


def resolve_release(required_sha):
    repo = os.environ["GITHUB_REPOSITORY"]
    revision = os.environ["GITHUB_SHA"]
    images = [
        read_json("aws", "ecr", "describe-images", "--repository-name", f"mediroute-{component}",
                  "--filter", "tagStatus=TAGGED", "--output", "json")["imageDetails"]
        for component in COMPONENTS
    ]
    pairs = release_candidates(*images)
    if not required_sha:
        history = subprocess.check_output(
            ["git", "rev-list", "--first-parent", revision], text=True, timeout=30,
        ).splitlines()
        main_order = {sha: index for index, sha in enumerate(history)}
        pairs.sort(key=lambda pair: main_order.get(pair["sha"], len(history)))
    for pair in pairs:
        sha = pair["sha"]
        if required_sha and sha != required_sha:
            continue
        exists = subprocess.run(["git", "cat-file", "-e", f"{sha}^{{commit}}"], capture_output=True)
        if exists.returncode:
            continue
        ancestry = subprocess.run(["git", "merge-base", "--is-ancestor", sha, revision], check=False)
        if ancestry.returncode == 1:
            continue
        ancestry.check_returncode()
        runs = read_json("gh", "api",
                         f"repos/{repo}/actions/workflows/ci.yml/runs?head_sha={sha}&event=push&per_page=100")
        if any(run["head_sha"] == sha and run["event"] == "push"
               and run["head_branch"] in {"main", "feature/aws_deployment"}
               and run["conclusion"] == "success"
               and (run.get("head_repository") or {}).get("full_name", "").lower() == repo.lower()
               for run in runs["workflow_runs"]):
            return pair
    raise SystemExit("STOP: No matching ECR backend/frontend release on main with successful push CI")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    window = commands.add_parser("deadline")
    window.add_argument("--max-minutes", type=int, default=1440)
    release = commands.add_parser("release")
    release.add_argument("--sha")
    args = parser.parse_args()
    if args.command == "deadline":
        deadline = stop_deadline(datetime.now(timezone.utc), args.max_minutes)
        if deadline is None:
            print("Demo starts are allowed 8 AM IST through midnight, until December 6, 2026.",
                  file=sys.stderr)
            return 3
        print(deadline.strftime("%Y-%m-%dT%H:%M:%S"))
    else:
        print(json.dumps(resolve_release(args.sha)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
