"""Guarded AWS-native start/stop for the short academic testing window.

Only the CI publication role writes the approved, digest-pinned release pointer.
No GitHub credentials, application keys, or DNS tokens enter this function.
"""
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

from demo_session import IST, FIRST_DAY, LAST_DAY, stop_deadline

ACCOUNT = "299952487175"
REGION = "ap-southeast-2"
CLUSTER = "mediroute-demo"
CLUSTER_ARN = f"arn:aws:ecs:{REGION}:{ACCOUNT}:cluster/{CLUSTER}"
TASK_PREFIX = f"arn:aws:ecs:{REGION}:{ACCOUNT}:task/{CLUSTER}/"
DEFINITION_PREFIX = f"arn:aws:ecs:{REGION}:{ACCOUNT}:task-definition/{CLUSTER}:"
REGISTRY = f"{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com"
RELEASE_PARAMETER = "/mediroute/dev/demo/release"
LOCK_TABLE = "mediroute-demo-control-lock"
STOP_ROLE = f"arn:aws:iam::{ACCOUNT}:role/mediroute-demo-scheduler-stop"
NETWORK = {"awsvpcConfiguration": {
    "subnets": ["subnet-0838d819c31bb2b38"],
    "securityGroups": ["sg-04dd5792bd86c3dc1"], "assignPublicIp": "ENABLED",
}}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_release(release, task):
    require(re.fullmatch(r"[0-9a-f]{40}", release.get("sha", "")), "Invalid release SHA")
    require(re.fullmatch(re.escape(DEFINITION_PREFIX) + r"[0-9]+",
                         release.get("task_definition", "")), "Invalid task definition ARN")
    require(task["taskDefinitionArn"] == release["task_definition"], "Task definition mismatch")
    require(task["status"] == "ACTIVE" and task["family"] == CLUSTER, "Inactive/wrong task family")
    require(task["cpu"] == "1024" and task["memory"] == "4096", "Unexpected task size")
    require(task["networkMode"] == "awsvpc" and "FARGATE" in task["requiresCompatibilities"],
            "Unexpected task network/launch type")
    for field, role in [("executionRoleArn", "mediroute-demo-task-execution"),
                        ("taskRoleArn", "mediroute-demo-task")]:
        require(task[field] == f"arn:aws:iam::{ACCOUNT}:role/{role}", "Unexpected IAM role")
    containers = {c["name"]: c for c in task["containerDefinitions"]}
    require(set(containers) == {"api", "frontend"}, "Expected DuckDNS containers")
    for name, component in [("api", "backend"), ("frontend", "frontend")]:
        digest = release.get(component, "")
        require(re.fullmatch(r"sha256:[0-9a-f]{64}", digest), "Invalid release digest")
        require(containers[name]["image"] == f"{REGISTRY}/mediroute-{component}@{digest}",
                "Task image does not match the approved release")
    env = {e["name"]: e["value"] for e in containers["frontend"].get("environment", [])}
    require(env.get("MEDIROUTE_DUCKDNS_LABEL") == "mediroute-demo", "Unexpected public hostname")
    ports = containers["frontend"].get("portMappings", [])
    require(len(ports) == 1 and ports[0].get("containerPort") == 443 and
            ports[0].get("hostPort", 443) == 443 and ports[0].get("protocol") == "tcp",
            "Unexpected public port")


def ensure_stop(scheduler, task_arn, deadline):
    require(task_arn.startswith(TASK_PREFIX), "Unexpected task ARN")
    name = "mediroute-stop-" + task_arn.rsplit("/", 1)[-1]
    expression = "at(" + deadline.strftime("%Y-%m-%dT%H:%M:%S") + ")"
    target = {
        "Arn": "arn:aws:scheduler:::aws-sdk:ecs:stopTask", "RoleArn": STOP_ROLE,
        "Input": json.dumps({"Cluster": CLUSTER_ARN, "Task": task_arn,
                            "Reason": "MediRoute midnight IST safety stop"}),
        "RetryPolicy": {"MaximumRetryAttempts": 3, "MaximumEventAgeInSeconds": 300},
    }
    expected = dict(Name=name, GroupName="default", ScheduleExpression=expression,
                    ScheduleExpressionTimezone="UTC", State="ENABLED",
                    FlexibleTimeWindow={"Mode": "OFF"}, ActionAfterCompletion="DELETE",
                    Target=target)
    try:
        scheduler.create_schedule(**expected)
    except scheduler.exceptions.ConflictException:
        pass
    actual = scheduler.get_schedule(Name=name, GroupName="default")
    for key in ("ScheduleExpression", "ScheduleExpressionTimezone", "State",
                "FlexibleTimeWindow", "ActionAfterCompletion"):
        require(actual[key] == expected[key], "Stop schedule mismatch: " + key)
    require(actual["Target"]["Arn"] == target["Arn"] and
            actual["Target"]["RoleArn"] == STOP_ROLE and
            json.loads(actual["Target"]["Input"]) == json.loads(target["Input"]),
            "Stop schedule has the wrong target")
    return name


def active_tasks(ecs):
    result = []
    for page in ecs.get_paginator("list_tasks").paginate(cluster=CLUSTER, desiredStatus="RUNNING"):
        result.extend(page["taskArns"])
    return result


def execute(event, ecs, scheduler, ssm, now):
    operation = event.get("operation")
    require(operation in {"start", "stop", "verify"}, "Invalid operation")
    # A read-only event proves Scheduler -> Lambda -> AWS access without replacing a task.
    if operation == "verify":
        release = json.loads(ssm.get_parameter(Name=RELEASE_PARAMETER)["Parameter"]["Value"])
        task = ecs.describe_task_definition(taskDefinition=release["task_definition"])["taskDefinition"]
        validate_release(release, task)
        return {"status": "verified", "source_sha": release["sha"], "tasks": active_tasks(ecs)}
    scheduled = event.get("scheduled", False)
    if scheduled:
        # Reject stale/replayed morning invocations rather than restarting a manually stopped app.
        stamp = datetime.fromisoformat(event["scheduled_time"].replace("Z", "+00:00"))
        age = now - stamp
        if not timedelta(0) <= age <= timedelta(minutes=15):
            return {"status": "skipped", "reason": "stale scheduled event"}
        local = stamp.astimezone(IST)
        if operation == "start":
            require(FIRST_DAY <= local.date() <= LAST_DAY and local.hour == 8 and local.minute == 0,
                    "Not an authorized morning event")
        else:
            require(FIRST_DAY < local.date() <= LAST_DAY + timedelta(days=1) and
                    local.hour == 0 and local.minute == 0, "Not an authorized midnight event")
    tasks = active_tasks(ecs)
    if operation == "stop":
        for arn in tasks:
            require(arn.startswith(TASK_PREFIX), "Unexpected task")
            ecs.stop_task(cluster=CLUSTER, task=arn, reason="MediRoute requested/midnight stop")
        return {"status": "stopped", "tasks": tasks}
    deadline = stop_deadline(now)
    if deadline is None:
        return {"status": "skipped", "reason": "outside academic testing hours"}
    require(len(tasks) <= 1, "More than one demo task exists; operator intervention needed")
    if tasks:
        schedule = ensure_stop(scheduler, tasks[0], deadline)
        return {"status": "already_running", "task_arn": tasks[0],
                "schedule_name": schedule, "stop_time_utc": deadline.isoformat()}
    release = json.loads(ssm.get_parameter(Name=RELEASE_PARAMETER)["Parameter"]["Value"])
    if event.get("required_sha"):
        require(release["sha"] == event["required_sha"], "Requested release is not prepared")
    definition = ecs.describe_task_definition(taskDefinition=release["task_definition"])["taskDefinition"]
    validate_release(release, definition)
    identity = event.get("request_id")
    if scheduled:
        identity = "morning-" + stamp.astimezone(IST).date().isoformat()
    require(isinstance(identity, str) and 1 <= len(identity) <= 200, "Missing request id")
    token = hashlib.sha256(identity.encode()).hexdigest()
    started_by = "mediroute-" + token[:26]
    task_arn = None
    try:
        response = ecs.run_task(
            cluster=CLUSTER, taskDefinition=release["task_definition"], launchType="FARGATE",
            count=1, clientToken=token, startedBy=started_by, networkConfiguration=NETWORK)
        require(not response.get("failures") and len(response.get("tasks", [])) == 1,
                "ECS launch failed")
        task_arn = response["tasks"][0]["taskArn"]
        require(response["tasks"][0].get("lastStatus") != "STOPPED",
                "This request already ran and was stopped; use a new manual request")
        schedule = ensure_stop(scheduler, task_arn, deadline)
    except Exception:
        # Also recover from a lost RunTask response. An independent midnight sweep remains in place.
        recovery = [task_arn] if task_arn else ecs.list_tasks(
            cluster=CLUSTER, startedBy=started_by).get("taskArns", [])
        for arn in recovery:
            ecs.stop_task(cluster=CLUSTER, task=arn, reason="MediRoute stop verification failed")
        raise
    return {"status": "started", "task_arn": task_arn, "source_sha": release["sha"],
            "task_definition": release["task_definition"], "schedule_name": schedule,
            "stop_time_utc": deadline.isoformat()}



def run_locked(event, ecs, scheduler, ssm, dynamodb, now, owner):
    if event.get("operation") == "verify":
        return execute(event, ecs, scheduler, ssm, now)
    key = {"Control": {"S": CLUSTER}}
    # The lease outlives the function's 120-second timeout. A terminated invocation
    # cannot overlap its successor; conditional deletion cannot release another owner.
    try:
        dynamodb.update_item(
            TableName=LOCK_TABLE, Key=key,
            UpdateExpression="SET #owner = :owner, #expires = :expires",
            ConditionExpression="attribute_not_exists(#expires) OR #expires < :now",
            ExpressionAttributeNames={"#owner": "Owner", "#expires": "ExpiresAt"},
            ExpressionAttributeValues={":owner": {"S": owner},
                                       ":expires": {"N": str(int(now.timestamp()) + 180)},
                                       ":now": {"N": str(int(now.timestamp()))}})
    except dynamodb.exceptions.ConditionalCheckFailedException:
        raise RuntimeError("Demo controller busy; retry shortly") from None
    try:
        return execute(event, ecs, scheduler, ssm, now)
    finally:
        try:
            dynamodb.delete_item(
                TableName=LOCK_TABLE, Key=key, ConditionExpression="#owner = :owner",
                ExpressionAttributeNames={"#owner": "Owner"},
                ExpressionAttributeValues={":owner": {"S": owner}})
        except dynamodb.exceptions.ConditionalCheckFailedException:
            pass


def handler(event, context):
    import boto3
    from botocore.config import Config
    config = Config(connect_timeout=3, read_timeout=10, retries={"max_attempts": 2})
    clients = [boto3.client(service, region_name=REGION, config=config)
               for service in ("ecs", "scheduler", "ssm", "dynamodb")]
    result = run_locked(event, *clients, datetime.now(timezone.utc), context.aws_request_id)
    print(json.dumps(result))
    return result
