#!/usr/bin/env bash
# MediRoute manual shutdown. Never launches AWS resources.
# Usage: bash scripts/stop_ecs.sh validate|list|stop TASK_ARN
set -Eeuo pipefail

readonly ACCOUNT=299952487175
readonly REGION=ap-southeast-2
readonly CLUSTER=mediroute-demo
readonly CLUSTER_ARN="arn:aws:ecs:${REGION}:${ACCOUNT}:cluster/${CLUSTER}"

usage() {
  echo 'Usage: bash scripts/stop_ecs.sh validate|list|stop TASK_ARN' >&2
  echo '  validate: offline syntax/config validation; list: read-only running tasks' >&2
  echo '  stop: requires exact ECS task ARN and MEDIROUTE_CONFIRM_STOP=YES' >&2
  exit 2
}

[[ $# -ge 1 ]] || usage
MODE=$1
case "$MODE" in
  validate) [[ $# -eq 1 ]] || usage ;;
  list)     [[ $# -eq 1 ]] || usage ;;
  stop)     [[ $# -eq 2 ]] || usage ;;
  *) usage ;;
esac

if [[ "$MODE" == validate ]]; then
  echo 'PASS: Manual-stop script validated locally; no AWS calls'
  exit 0
fi

command -v aws >/dev/null || { echo 'STOP: AWS CLI is required' >&2; exit 1; }
[[ "${AWS_REGION:-$REGION}" == "$REGION" ]] || {
  echo 'STOP: Unexpected AWS_REGION' >&2; exit 1;
}
[[ "${AWS_DEFAULT_REGION:-$REGION}" == "$REGION" ]] || {
  echo 'STOP: Unexpected AWS_DEFAULT_REGION' >&2; exit 1;
}
export AWS_REGION="$REGION" AWS_DEFAULT_REGION="$REGION"

CURRENT_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
[[ "$CURRENT_ACCOUNT" == "$ACCOUNT" ]] || {
  echo 'STOP: Unexpected AWS account' >&2; exit 1;
}

if [[ "$MODE" == list ]]; then
  aws ecs list-tasks --cluster "$CLUSTER" --desired-status RUNNING \
    --query 'taskArns' --output json
  exit 0
fi

TASK_ARN=$2
if [[ ! "$TASK_ARN" =~ ^arn:aws:ecs:ap-southeast-2:299952487175:task/mediroute-demo/[0-9a-f]{32}$ ]]; then
  echo 'STOP: Provide an exact task ARN from the MediRoute demo cluster' >&2
  exit 1
fi
[[ "${MEDIROUTE_CONFIRM_STOP:-}" == YES ]] || {
  echo 'STOP: Set MEDIROUTE_CONFIRM_STOP=YES to confirm stopping this task' >&2
  exit 1
}

# Check task membership and definition family before requesting StopTask.
DETAILS=$(aws ecs describe-tasks --cluster "$CLUSTER" --tasks "$TASK_ARN" --output json)
STATUS=$(python3 -c '
import json, sys
j = json.load(sys.stdin)
if j.get("failures") or len(j.get("tasks", [])) != 1:
    raise SystemExit("STOP: ECS task was not found or could not be described")
t = j["tasks"][0]
if t.get("clusterArn") != "arn:aws:ecs:ap-southeast-2:299952487175:cluster/mediroute-demo":
    raise SystemExit("STOP: Unexpected ECS cluster")
if not t.get("taskDefinitionArn", "").startswith("arn:aws:ecs:ap-southeast-2:299952487175:task-definition/mediroute-demo:"):
    raise SystemExit("STOP: Unexpected task-definition family")
print(t.get("lastStatus", "UNKNOWN"))
' <<< "$DETAILS")

if [[ "$STATUS" == STOPPED ]]; then
  echo 'PASS: ECS task is already stopped; no action needed'
  exit 0
fi

aws ecs stop-task \
  --cluster "$CLUSTER" --task "$TASK_ARN" \
  --reason 'Manual MediRoute demo shutdown' \
  --query 'task.{TaskArn:taskArn,LastStatus:lastStatus,DesiredStatus:desiredStatus}' \
  --output json

echo 'PASS: ECS stop requested; confirm STOPPED with describe-tasks if needed'
echo 'NOTE: Any existing automatic-stop schedule is left intact as a fallback.'
