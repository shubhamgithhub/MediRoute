#!/usr/bin/env bash
# MediRoute: validate ECS template, register task definition, or guarded Fargate launch.
# Requires AWS CLI v2, Python 3 with PyYAML, and the existing render_ecs_task.py.
set -Eeuo pipefail

usage() {
  echo 'Usage: bash scripts/deploy_ecs.sh validate|register|deploy' >&2
  echo '  validate: local checks only; register: AWS task definition only' >&2
  echo '  deploy: one billable task with a verified automatic stop schedule' >&2
  exit 2
}
[[ $# == 1 ]] || usage
MODE=$1
case "$MODE" in validate|register|deploy) ;; *) usage ;; esac

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT_DIR"
python3 scripts/render_ecs_task.py validate
TTL_MINUTES=$(
  python3 scripts/check_deployment_policy.py infra/deployment-control.yaml local false true |
    python3 -c '
import json, os, sys
local_limit = json.load(sys.stdin)["max_runtime_minutes"]
trusted = os.environ.get("MEDIROUTE_TRUSTED_MAX_RUNTIME_MINUTES")
if trusted is None:
    print(local_limit)
else:
    try:
        trusted_limit = int(trusted)
    except ValueError:
        raise SystemExit("STOP: Invalid trusted runtime limit") from None
    if trusted_limit < 1:
        raise SystemExit("STOP: Invalid trusted runtime limit")
    print(min(local_limit, trusted_limit))
'
)
echo "PASS: Deployment safety policy valid (scheduled stop after ${TTL_MINUTES} minutes)"
if [[ "$MODE" == validate ]]; then
  echo 'PASS: Validation only; no AWS calls or charges'
  exit 0
fi

# Keep the account, subnet and IAM role fixed. DuckDNS selects its own HTTPS security group.
readonly ACCOUNT=299952487175
readonly REGION=ap-southeast-2
readonly CLUSTER=mediroute-demo
readonly CLUSTER_ARN="arn:aws:ecs:${REGION}:${ACCOUNT}:cluster/${CLUSTER}"
readonly REGISTRY="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"
readonly STOP_ROLE_ARN="arn:aws:iam::${ACCOUNT}:role/mediroute-demo-scheduler-stop"
readonly SUBNET=subnet-0838d819c31bb2b38
readonly SECURITY_GROUP=sg-016b1b2e95195c069
readonly SECRET_ARN="arn:aws:ssm:${REGION}:${ACCOUNT}:parameter/mediroute/dev/openrouter/api-key"
export MEDIROUTE_ENDPOINT_MODE="${MEDIROUTE_ENDPOINT_MODE:-quick-tunnel}"
readonly ENDPOINT_MODE="$MEDIROUTE_ENDPOINT_MODE"
TASK_SECURITY_GROUP="$SECURITY_GROUP"
case "$ENDPOINT_MODE" in
  quick-tunnel) ;;
  duckdns)
    [[ "${MEDIROUTE_DUCKDNS_SECURITY_GROUP:-}" =~ ^sg-([0-9a-f]{8}|[0-9a-f]{17})$ &&
       "$MEDIROUTE_DUCKDNS_SECURITY_GROUP" != "$SECURITY_GROUP" ]] || {
      echo 'STOP: Set a separate MEDIROUTE_DUCKDNS_SECURITY_GROUP for HTTPS' >&2
      exit 1
    }
    TASK_SECURITY_GROUP="$MEDIROUTE_DUCKDNS_SECURITY_GROUP"
    ;;
  *) echo 'STOP: Invalid MEDIROUTE_ENDPOINT_MODE' >&2; exit 1 ;;
esac
readonly TASK_SECURITY_GROUP
readonly CLOUDFLARED_PIN='cloudflare/cloudflared@sha256:b94b96edf2c9c4360f8879c8580cfaa99077f19c849ec595ca2f711b27d4f344'

[[ "${AWS_REGION:-$REGION}" == "$REGION" ]] || { echo 'STOP: Unexpected AWS_REGION' >&2; exit 1; }
[[ "${AWS_DEFAULT_REGION:-$REGION}" == "$REGION" ]] || { echo 'STOP: Unexpected AWS_DEFAULT_REGION' >&2; exit 1; }
export AWS_REGION="$REGION" AWS_DEFAULT_REGION="$REGION"
[[ "$(aws sts get-caller-identity --query Account --output text)" == "$ACCOUNT" ]] || {
  echo 'STOP: Wrong AWS account' >&2; exit 1;
}

: "${BACKEND_IMAGE:?Set BACKEND_IMAGE to an immutable ECR image digest}"
: "${FRONTEND_IMAGE:?Set FRONTEND_IMAGE to an immutable ECR image digest}"
[[ "${BACKEND_IMAGE%@sha256:*}" == "$REGISTRY/mediroute-backend" && "$BACKEND_IMAGE" =~ @sha256:[0-9a-f]{64}$ ]] || {
  echo 'STOP: BACKEND_IMAGE must be the MediRoute backend ECR digest' >&2; exit 1;
}
[[ "${FRONTEND_IMAGE%@sha256:*}" == "$REGISTRY/mediroute-frontend" && "$FRONTEND_IMAGE" =~ @sha256:[0-9a-f]{64}$ ]] || {
  echo 'STOP: FRONTEND_IMAGE must be the MediRoute frontend ECR digest' >&2; exit 1;
}

export TASK_CPU=1024 TASK_MEMORY=4096
export TASK_EXECUTION_ROLE_ARN="arn:aws:iam::${ACCOUNT}:role/mediroute-demo-task-execution"
export TASK_ROLE_ARN="arn:aws:iam::${ACCOUNT}:role/mediroute-demo-task"
export CLOUDFLARED_IMAGE="$CLOUDFLARED_PIN"
export LOG_GROUP=/ecs/mediroute-demo
export OPENROUTER_API_KEY_PARAMETER_ARN="$SECRET_ARN"

TMP_DIR=$(mktemp -d)
TASK_ARN=''
STARTED_BY=''
LAUNCH_ATTEMPTED=false
SCHEDULE_VERIFIED=false
cleanup() {
  status=$?
  trap - EXIT
  if [[ "$status" -ne 0 && "$LAUNCH_ATTEMPTED" == true && "$SCHEDULE_VERIFIED" != true ]]; then
    echo 'WARNING: Launch/schedule verification failed; requesting emergency ECS stop.' >&2
    # A lost RunTask response might leave the ARN unknown. Find task by unique started-by token.
    if [[ -z "$TASK_ARN" && -n "$STARTED_BY" ]]; then
      TASK_ARN=$(aws ecs list-tasks --cluster "$CLUSTER" \
        --started-by "$STARTED_BY" --query 'taskArns[0]' --output text 2>/dev/null || true)
      [[ "$TASK_ARN" == None ]] && TASK_ARN=''
    fi
    if [[ -n "$TASK_ARN" ]]; then
      aws ecs stop-task --cluster "$CLUSTER" --task "$TASK_ARN" \
        --reason 'MediRoute: automatic stop schedule not verified' \
        --query 'task.taskArn' --output text >&2 || \
        echo 'CRITICAL: Emergency stop failed; stop the task manually.' >&2
    else
      echo 'CRITICAL: Could not identify launched task; check cluster immediately.' >&2
    fi
  fi
  rm -rf -- "$TMP_DIR"
  exit "$status"
}
trap cleanup EXIT

python3 scripts/render_ecs_task.py render > "$TMP_DIR/task.json"
python3 - "$TMP_DIR/task.json" "$ENDPOINT_MODE" <<'PY'
import json, sys
x = json.load(open(sys.argv[1]))
assert x['family'] == 'mediroute-demo'
assert str(x['cpu']) == '1024' and str(x['memory']) == '4096'
expected = ['api', 'frontend'] if sys.argv[2] == 'duckdns' else ['api', 'frontend', 'tunnel']
assert [c['name'] for c in x['containerDefinitions']] == expected
if sys.argv[2] == 'duckdns':
    assert x['containerDefinitions'][1]['portMappings'] == [{'containerPort': 443, 'protocol': 'tcp'}]
assert x['containerDefinitions'][0]['secrets'] == [{
    'name':'OPENROUTER_API_KEY',
    'valueFrom':'arn:aws:ssm:ap-southeast-2:299952487175:parameter/mediroute/dev/openrouter/api-key'}]
print('PASS: Rendered task definition validated')
PY

# Confirm billable operation and check existing tasks BEFORE any AWS write.
if [[ "$MODE" == deploy ]]; then
  [[ "${MEDIROUTE_CONFIRM_BILLABLE_RUN:-}" == 'YES' ]] || {
    echo 'STOP: Set MEDIROUTE_CONFIRM_BILLABLE_RUN=YES for the billable deploy command' >&2
    exit 1
  }
  # GitHub workflow must also use a shared concurrency group across BOTH branches.
  TASK_COUNT=$(aws ecs list-tasks --cluster "$CLUSTER" --desired-status RUNNING \
    --query 'length(taskArns)' --output text)
  [[ "$TASK_COUNT" == 0 ]] || {
    echo "STOP: $TASK_COUNT task(s) already desired RUNNING" >&2; exit 1;
  }
fi

# Registration does not start compute. Only do this after local validation.
TASK_DEF_ARN=$(aws ecs register-task-definition --cli-input-json "file://$TMP_DIR/task.json" \
  --query 'taskDefinition.taskDefinitionArn' --output text)
[[ "$TASK_DEF_ARN" == "arn:aws:ecs:${REGION}:${ACCOUNT}:task-definition/mediroute-demo:"* ]] || {
  echo 'STOP: Unexpected registered task definition ARN' >&2; exit 1;
}
echo "PASS: Registered $TASK_DEF_ARN"
if [[ "$MODE" == register ]]; then
  echo 'PASS: No Fargate task launched'
  exit 0
fi

STARTED_BY="mediroute-$(date -u +%Y%m%d%H%M%S)-$(python3 - <<'PY'
import uuid
print(uuid.uuid4().hex[:8])
PY
)"
CLIENT_TOKEN=$(python3 - <<'PY'
import uuid
print(uuid.uuid4())
PY
)

# Recheck the window after image preparation so a delayed job cannot start after midnight.
DEMO_STOP_AT=''
if [[ "${MEDIROUTE_DEMO_WINDOW:-}" == YES ]]; then
  DEMO_STOP_AT=$(python3 scripts/demo_session.py deadline --max-minutes "$TTL_MINUTES")
fi

LAUNCH_ATTEMPTED=true
aws ecs run-task \
  --cluster "$CLUSTER" \
  --task-definition "$TASK_DEF_ARN" \
  --launch-type FARGATE \
  --count 1 \
  --started-by "$STARTED_BY" \
  --client-token "$CLIENT_TOKEN" \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET],securityGroups=[$TASK_SECURITY_GROUP],assignPublicIp=ENABLED}" \
  --output json > "$TMP_DIR/run.json"
TASK_ARN=$(python3 - "$TMP_DIR/run.json" <<'PY'
import json, sys
x = json.load(open(sys.argv[1]))
tasks = x.get('tasks') or []
print(tasks[0]['taskArn'] if len(tasks) == 1 else '')
PY
)
python3 - "$TMP_DIR/run.json" <<'PY'
import json, sys
x=json.load(open(sys.argv[1]))
if x.get('failures') or len(x.get('tasks',[])) != 1:
    raise SystemExit('STOP: RunTask reported failures or unexpected task count')
PY
[[ "$TASK_ARN" == "arn:aws:ecs:${REGION}:${ACCOUNT}:task/${CLUSTER}/"* ]] || {
  echo 'STOP: Unexpected ECS task ARN' >&2; exit 1;
}
echo "PASS: Launched $TASK_ARN"

STOP_AT="$DEMO_STOP_AT"
if [[ -z "$STOP_AT" ]]; then
  STOP_AT=$(date -u -d "+${TTL_MINUTES} minutes" +%Y-%m-%dT%H:%M:%S)
elif [[ "$STOP_AT" < "$(date -u -d '+1 minute' +%Y-%m-%dT%H:%M:%S)" ]]; then
  echo 'STOP: Too late to verify the required demo stop schedule' >&2
  exit 1
fi
STOP_EXPR="at(${STOP_AT})"
SCHEDULE_NAME="mediroute-stop-$(date -u +%Y%m%d%H%M%S)-$(python3 - <<'PY'
import uuid
print(uuid.uuid4().hex[:8])
PY
)"
python3 - "$TMP_DIR/target.json" "$CLUSTER_ARN" "$TASK_ARN" "$STOP_ROLE_ARN" <<'PY'
import json, sys
path, cluster, task, role = sys.argv[1:]
target = {
  'Arn': 'arn:aws:scheduler:::aws-sdk:ecs:stopTask',
  'RoleArn': role,
  'Input': json.dumps({'Cluster':cluster, 'Task':task,
                       'Reason':'MediRoute demo automatic safety stop'}),
  'RetryPolicy': {'MaximumRetryAttempts':3,'MaximumEventAgeInSeconds':300}
}
with open(path, 'w') as f: json.dump(target,f)
PY
aws scheduler create-schedule \
  --name "$SCHEDULE_NAME" --group-name default \
  --schedule-expression "$STOP_EXPR" --schedule-expression-timezone UTC \
  --state ENABLED --flexible-time-window Mode=OFF \
  --action-after-completion DELETE \
  --target "file://$TMP_DIR/target.json" --output json > "$TMP_DIR/create.json"
aws scheduler get-schedule --name "$SCHEDULE_NAME" --group-name default \
  --output json > "$TMP_DIR/schedule.json"
python3 - "$TMP_DIR/schedule.json" "$TASK_ARN" "$CLUSTER_ARN" "$STOP_EXPR" "$STOP_ROLE_ARN" <<'PY'
import json, sys
path, task, cluster, expected_expr, expected_role = sys.argv[1:]
s = json.load(open(path))
target = s['Target']
payload = json.loads(target['Input'])
assert s['State'] == 'ENABLED'
assert s['ScheduleExpression'] == expected_expr
assert s['ScheduleExpressionTimezone'] == 'UTC'
assert s['ActionAfterCompletion'] == 'DELETE'
assert s['FlexibleTimeWindow']['Mode'] == 'OFF'
assert target['Arn'] == 'arn:aws:scheduler:::aws-sdk:ecs:stopTask'
assert target['RoleArn'] == expected_role
assert payload['Task'] == task and payload['Cluster'] == cluster
print('PASS: Stop schedule enabled and targeting the exact ECS task')
PY
SCHEDULE_VERIFIED=true
printf 'TASK_ARN=%s\nSCHEDULE_NAME=%s\nSTOP_TIME_UTC=%s\n' \
  "$TASK_ARN" "$SCHEDULE_NAME" "$STOP_AT"
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  printf 'task_arn=%s\nschedule_name=%s\nstop_time_utc=%s\ntask_definition_arn=%s\n' \
    "$TASK_ARN" "$SCHEDULE_NAME" "$STOP_AT" "$TASK_DEF_ARN" >> "$GITHUB_OUTPUT"
fi
