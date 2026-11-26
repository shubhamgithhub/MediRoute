"""Install the AWS-native academic demo schedule (explicit --apply required).

Uses the operator's existing AWS CLI profile. It does not read application secrets.
The optional bootstrap file is non-secret metadata for an already verified main release.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile

from demo_controller import (ACCOUNT, REGION, CLUSTER_ARN, TASK_PREFIX, DEFINITION_PREFIX,
                             RELEASE_PARAMETER, STOP_ROLE, LOCK_TABLE, validate_release)

FUNCTION = "mediroute-demo-control"
FUNCTION_ARN = f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:{FUNCTION}"
EXECUTION_ROLE = "mediroute-demo-control"
TRIGGER_ROLE = "mediroute-demo-daily-scheduler"
LOG_GROUP = "/aws/lambda/" + FUNCTION
ROOT = Path(__file__).resolve().parents[1]


def aws(service, operation, optional=False, **data):
    args = ["aws", service, operation, "--region", REGION, "--output", "json"]
    if data:
        args += ["--cli-input-json", json.dumps(data)]
    result = subprocess.run(args, capture_output=True, text=True, timeout=90)
    if result.returncode:
        if optional and any(name in result.stderr for name in
                            ("NoSuchEntity", "ResourceNotFoundException", "ResourceAlreadyExistsException")):
            return None
        raise RuntimeError(f"{service} {operation}: {result.stderr}")
    return json.loads(result.stdout) if result.stdout.strip() else {}


def statement(actions, resources, **extra):
    return {"Effect": "Allow", "Action": actions, "Resource": resources, **extra}


def policy(statements):
    return {"Version": "2012-10-17", "Statement": statements}


def role(name, service, statements, condition=None):
    trust = {"Effect": "Allow", "Principal": {"Service": service}, "Action": "sts:AssumeRole"}
    if condition:
        trust["Condition"] = condition
    assume = json.dumps(policy([trust]))
    if aws("iam", "get-role", optional=True, RoleName=name):
        aws("iam", "update-assume-role-policy", RoleName=name, PolicyDocument=assume)
    else:
        aws("iam", "create-role", RoleName=name, AssumeRolePolicyDocument=assume)
    aws("iam", "put-role-policy", RoleName=name, PolicyName="MediRouteDailyDemo",
        PolicyDocument=json.dumps(policy(statements)))
    return f"arn:aws:iam::{ACCOUNT}:role/{name}"


def schedule(name, expression, timezone_name, target, **extra):
    data = dict(Name=name, GroupName="default", ScheduleExpression=expression,
                ScheduleExpressionTimezone=timezone_name, FlexibleTimeWindow={"Mode": "OFF"},
                State="ENABLED", ActionAfterCompletion="DELETE", Target=target, **extra)
    existing = aws("scheduler", "get-schedule", optional=True, Name=name, GroupName="default")
    aws("scheduler", "update-schedule" if existing else "create-schedule", **data)
    actual = aws("scheduler", "get-schedule", Name=name, GroupName="default")
    for field in ("ScheduleExpression", "ScheduleExpressionTimezone", "State", "FlexibleTimeWindow",
                  "ActionAfterCompletion", "Target"):
        if actual[field] != data[field]:
            raise RuntimeError("Schedule verification failed: " + field)
    print(json.dumps({key: actual.get(key) for key in
                      ("Name", "State", "ScheduleExpression", "ScheduleExpressionTimezone", "EndDate")}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--bootstrap-release", type=Path)
    parser.add_argument("--probe", action="store_true",
                        help="Schedule a read-only controller verification two minutes from now")
    args = parser.parse_args()
    if not args.apply:
        raise SystemExit("Use --apply to install the daily AWS control infrastructure.")
    if aws("sts", "get-caller-identity")["Account"] != ACCOUNT:
        raise SystemExit("Wrong AWS account")
    # These permissions cannot read the application's SSM secrets or change infrastructure.
    cluster_condition = {"ArnEquals": {"ecs:cluster": CLUSTER_ARN}}
    execution = role(EXECUTION_ROLE, "lambda.amazonaws.com", [
        statement(["logs:CreateLogStream", "logs:PutLogEvents"],
                  f"arn:aws:logs:{REGION}:{ACCOUNT}:log-group:{LOG_GROUP}:*"),
        statement(["dynamodb:UpdateItem", "dynamodb:DeleteItem"],
                  f"arn:aws:dynamodb:{REGION}:{ACCOUNT}:table/{LOCK_TABLE}"),
        statement("ssm:GetParameter", f"arn:aws:ssm:{REGION}:{ACCOUNT}:parameter{RELEASE_PARAMETER}"),
        statement("ecs:ListTasks", "*", Condition=cluster_condition),
        statement("ecs:DescribeTaskDefinition", DEFINITION_PREFIX + "*"),
        statement("ecs:RunTask", DEFINITION_PREFIX + "*", Condition=cluster_condition),
        statement("ecs:StopTask", TASK_PREFIX + "*", Condition=cluster_condition),
        statement(["scheduler:CreateSchedule", "scheduler:GetSchedule"],
                  f"arn:aws:scheduler:{REGION}:{ACCOUNT}:schedule/default/mediroute-stop-*"),
        statement("iam:PassRole", STOP_ROLE,
                  Condition={"StringEquals": {"iam:PassedToService": "scheduler.amazonaws.com"}}),
        statement("iam:PassRole", [f"arn:aws:iam::{ACCOUNT}:role/mediroute-demo-task",
                                  f"arn:aws:iam::{ACCOUNT}:role/mediroute-demo-task-execution"],
                  Condition={"StringEquals": {"iam:PassedToService": "ecs-tasks.amazonaws.com"}}),
    ])
    trigger = role(TRIGGER_ROLE, "scheduler.amazonaws.com",
                   [statement("lambda:InvokeFunction", FUNCTION_ARN)],
                   {"StringEquals": {"aws:SourceAccount": ACCOUNT},
                    "ArnEquals": {"aws:SourceArn": f"arn:aws:scheduler:{REGION}:{ACCOUNT}:schedule-group/default"}})
    aws("logs", "create-log-group", optional=True, logGroupName=LOG_GROUP)
    aws("logs", "put-retention-policy", logGroupName=LOG_GROUP, retentionInDays=7)
    if not aws("dynamodb", "describe-table", optional=True, TableName=LOCK_TABLE):
        aws("dynamodb", "create-table", TableName=LOCK_TABLE, BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[{"AttributeName": "Control", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "Control", "KeyType": "HASH"}])
    subprocess.run(["aws", "dynamodb", "wait", "table-exists", "--region", REGION,
                    "--table-name", LOCK_TABLE], check=True)
    with tempfile.TemporaryDirectory() as folder:
        archive = Path(folder) / "controller.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            for name in ("demo_controller.py", "demo_session.py"):
                bundle.write(ROOT / "scripts" / name, name)
        exists = aws("lambda", "get-function", optional=True, FunctionName=FUNCTION)
        config = dict(FunctionName=FUNCTION, Role=execution, Runtime="python3.12",
                      Handler="demo_controller.handler", Timeout=120, MemorySize=256,
                      Description="MediRoute 08:00-midnight IST demo through 2026-12-06")
        if exists:
            subprocess.run(["aws", "lambda", "update-function-code", "--region", REGION,
                            "--function-name", FUNCTION, "--zip-file", "fileb://" + str(archive)],
                           check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["aws", "lambda", "wait", "function-updated-v2", "--region", REGION,
                            "--function-name", FUNCTION], check=True)
            aws("lambda", "update-function-configuration", **config)
        else:
            # The CLI reads the zip locally; no deployment bucket or stored AWS credentials.
            subprocess.run(["aws", "lambda", "create-function", "--region", REGION,
                            "--cli-input-json", json.dumps(config), "--zip-file", "fileb://" + str(archive)],
                           check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["aws", "lambda", "wait", "function-active-v2", "--region", REGION,
                        "--function-name", FUNCTION], check=True)
        subprocess.run(["aws", "lambda", "wait", "function-updated-v2", "--region", REGION,
                        "--function-name", FUNCTION], check=True)
    # A conditional DynamoDB lease serializes controls even in accounts with only
    # ten Lambda slots, where AWS disallows reserving any function concurrency.
    aws("lambda", "put-function-event-invoke-config", FunctionName=FUNCTION,
        MaximumRetryAttempts=2, MaximumEventAgeInSeconds=900)
    aws("iam", "put-role-policy", RoleName="mediroute-github-deployment",
        PolicyName="MediRouteDailyDemoControl", PolicyDocument=json.dumps(policy([
            statement("lambda:InvokeFunction", FUNCTION_ARN),
            statement(["ssm:PutParameter", "ssm:GetParameter"],
                      f"arn:aws:ssm:{REGION}:{ACCOUNT}:parameter{RELEASE_PARAMETER}"),
        ])))
    if args.bootstrap_release:
        release = json.loads(args.bootstrap_release.read_text())
        definition = aws("ecs", "describe-task-definition",
                         taskDefinition=release["task_definition"])["taskDefinition"]
        validate_release(release, definition)
        for component in ("backend", "frontend"):
            image = aws("ecr", "describe-images", repositoryName="mediroute-" + component,
                        imageIds=[{"imageTag": "sha-" + release["sha"]}])["imageDetails"][0]
            if image["imageDigest"] != release[component]:
                raise SystemExit("Bootstrap image digest mismatch")
        aws("ssm", "put-parameter", Name=RELEASE_PARAMETER, Value=json.dumps(release),
            Type="String", Tier="Standard", Overwrite=True)
    # Ensure valid release metadata exists before enabling a schedule.
    release = json.loads(aws("ssm", "get-parameter", Name=RELEASE_PARAMETER)["Parameter"]["Value"])
    validate_release(release, aws("ecs", "describe-task-definition",
                                  taskDefinition=release["task_definition"])["taskDefinition"])
    target = {"Arn": FUNCTION_ARN, "RoleArn": trigger,
              "RetryPolicy": {"MaximumRetryAttempts": 3, "MaximumEventAgeInSeconds": 900}}
    for operation, expression, end in [
        ("start", "cron(0 8 * * ? 2026)", "2026-12-06T18:29:00Z"),
        ("stop", "cron(0 0 * * ? 2026)", "2026-12-06T18:45:00Z"),
    ]:
        payload = {"operation": operation, "scheduled": True,
                   "scheduled_time": "<aws.scheduler.scheduled-time>"}
        schedule("mediroute-demo-daily-" + operation, expression, "Asia/Kolkata",
                 {**target, "Input": json.dumps(payload)}, EndDate=end)
    if args.probe:
        when = datetime.now(timezone.utc) + timedelta(minutes=2)
        schedule("mediroute-demo-scheduler-probe", "at(" + when.strftime("%Y-%m-%dT%H:%M:%S") + ")",
                 "UTC", {**target, "Input": json.dumps({"operation": "verify"})})
    print("Installed daily startup, midnight sweep, and serialized manual controls; no ECS task replaced.")


if __name__ == "__main__":
    main()
