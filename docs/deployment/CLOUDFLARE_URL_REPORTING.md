# Cloudflare URL reporting

Manual ECS deploys and automatic deployments append a deployment report to the
GitHub Actions job summary after the guarded launch and stop-schedule verification
succeed. This change does not enable automatic deployment.

The report includes the deployed branch/commit, exact ECS task ARN, observed task
and health status, stop schedule/time (UTC), and the Quick Tunnel URL from that
task's CloudWatch stream. Automatic deployments use SOURCE_BRANCH/SOURCE_SHA,
not the workflow's main-branch checkout.

## Permissions

The existing GitHub deployment role already uses ecs:DescribeTasks for manual
shutdown. The additional policy in
infra/iam/github-cloudflare-url-logs-read.json grants logs:FilterLogEvents only
on /ecs/mediroute-demo in ap-southeast-2. This API is scoped to the log group;
the reporter further selects tunnel/tunnel/<exact-task-id> in its request.

The policy file is not automatically installed. An AWS operator can review and
apply it with the existing local profile:

```bash
aws iam put-role-policy --profile mediroute-local \
  --role-name mediroute-github-deployment \
  --policy-name MediRouteReadTunnelLogsForURL \
  --policy-document file://infra/iam/github-cloudflare-url-logs-read.json
```

No AWS changes are needed for the offline tests below.

## Failure behavior

URL discovery has a 150-second wall-clock budget; each AWS process is bounded
and CLI retries are disabled. Log ingestion/startup delays and temporary errors
are retried. Access denied is reported immediately. A separate bounded
DescribeTasks read obtains status even if the URL is missing.

Expected read/discovery failures produce warnings and a useful summary, with
UNKNOWN for unverified status. The reporting step also has a four-minute timeout
and continue-on-error, so an unexpected reporting failure cannot overturn the
successful guarded launch. It does not modify or remove the stop schedule.

A URL found in logs is not an end-to-end health check. Stopping/stopped tasks
show the URL as historical. No raw container logs, AWS error output, patient
details, or credentials are copied into the summary.

## Validation

In WSL, from ~/projects/MediRoute:

```bash
python3 scripts/test_report_cloudflare_url.py
bash scripts/deploy_ecs.sh validate
bash scripts/stop_ecs.sh validate
git diff --check
```

The reporting tests use only Python's standard library and mocked AWS reads.

After review/merge and IAM setup, test at the next deliberately requested manual
deployment: publish the exact passing commit's images, deploy that commit, then
check the summary URL, source SHA, task status and schedule against AWS. Verify
the application with synthetic data and confirm shutdown. Keep auto_deploy false.
Live AWS/GitHub validation is still required; offline checks do not prove that
the role permission has been installed or that a tunnel starts successfully.
