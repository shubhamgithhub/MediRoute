# Low-cost CloudWatch dashboard: manual setup

The code produces seven application metric series and a dashboard named
**MediRoute**. Container Insights stays disabled and auto_deploy stays false.
These files do not apply AWS changes automatically. No new application IAM
permissions are needed: EMF uses the existing awslogs log-delivery path.

## 1. Local checks (WSL)

```bash
cd ~/projects/MediRoute
python3 -B scripts/test_cloudwatch_metrics.py
python3 -B scripts/test_report_cloudflare_url.py
python3 monitoring/build_dashboard.py
git diff --check
```

Inspect the changed files before committing. Keep unrelated untracked files out
of the commit. Run CI, publish images for the exact passing commit, and perform a
deliberate manual ECS deployment when ready. The new task definition sets
MEDIROUTE_METRICS_ENABLED=true for the api container. Existing tasks/images do
not acquire instrumentation merely because a dashboard is created.

## 2. Confirm account and current settings (WSL; read-only)

```bash
export AWS_PROFILE=mediroute-local AWS_REGION=ap-southeast-2
aws sts get-caller-identity --query Account --output text
aws ecs describe-clusters --clusters mediroute-demo --include SETTINGS \
  --query 'clusters[0].settings' --output json
aws cloudwatch list-dashboards --dashboard-name-prefix MediRoute \
  --query 'DashboardEntries[].DashboardName' --output json
```

Account must be 299952487175. Stop if it differs. Inspect whether **MediRoute**
already exists: PutDashboard replaces the entire existing definition.
If it exists, save it before replacing:

```bash
mkdir -p /tmp/mediroute-dashboard-backups
aws cloudwatch get-dashboard --dashboard-name MediRoute \
  --query DashboardBody --output text \
  > "/tmp/mediroute-dashboard-backups/MediRoute-$(date -u +%Y%m%dT%H%M%SZ).json"
```

Keep that backup until the new dashboard has been verified.

## 3. Apply setup manually

Run only after the account check and any needed dashboard backup above.

```bash
aws ecs update-cluster-settings --cluster mediroute-demo \
  --settings name=containerInsights,value=disabled
aws logs put-retention-policy --log-group-name /ecs/mediroute-demo \
  --retention-in-days 3
aws cloudwatch put-dashboard --dashboard-name MediRoute \
  --dashboard-body file://monitoring/mediroute-dashboard.json
```

These commands do not start compute. The first explicitly disables Container
Insights for this cluster even if account defaults differ. The retention command
keeps the existing intended three-day policy; if retention was longer, older logs
become eligible for deletion. Skip that command if you need to preserve them.
PutDashboard should return DashboardValidationMessages: []; resolve any warnings.

The local operator needs ecs:UpdateClusterSettings for this cluster,
logs:PutRetentionPolicy for this log group and cloudwatch:PutDashboard for
arn:aws:cloudwatch::299952487175:dashboard/MediRoute, plus the read actions used
above. Do not grant broad administrator access or add these provisioning
permissions to the application/GitHub deployment role merely for telemetry.

## 4. Verify after deploying the instrumented image

Use synthetic data to submit a few queries in the public application. Then:

```bash
aws cloudwatch list-metrics --namespace MediRoute/Demo \
  --dimensions Name=Environment,Value=dev --output json
aws ecs describe-clusters --clusters mediroute-demo --include SETTINGS \
  --query 'clusters[0].settings' --output json
```

Open AWS Console > CloudWatch > Dashboards > MediRoute. Allow time for log
ingestion and metric discovery (new metrics may take up to 15 minutes to appear
in ListMetrics). Use a range containing the demo and select UTC for daily buckets.
After one normal query, Queries increases and QueryTimeMs has a sample; a valid
response normally has QueriesFailed=0 and QueriesRejected=0. A validation rejection
increments QueriesRejected, not QueriesFailed. LLMCalls includes actual retries.
LLMCostUSD can be absent while LLMCostMissing rises: do not interpret this as zero
spending. Rule-only queries need not produce any LLM metrics.

No metric filters need to be created. If all charts stay blank, verify the
deployed api environment flag, actual image SHA, plain JSON _aws events in
api/api/<task-id>, log delivery, and matching namespace/dimension. Inspect EMF
parsing/validation failures in AWS/Logs if needed. Retained graph data can outlive
the three-day source-log retention period.

## Cost and rollback

There are seven fixed metric series, one dashboard and small per-request logs.
Metric math and percentiles reuse those series. No Container Insights, public
dashboard sharing, periodic log queries or new compute is enabled. Free
allowances are shared with the rest of the AWS account. Review actual billing;
the dashboard is not a $10 spending cap. OpenRouter costs are billed separately.

To stop new telemetry, set MEDIROUTE_METRICS_ENABLED=false in the ECS template
and deploy that change deliberately. Deleting a dashboard alone does not stop
metrics ingestion. Keep auto_deploy false throughout. Restore a saved dashboard
with put-dashboard --dashboard-body file://<backup-path> if necessary.

Read METRICS_CONTRACT.md for exact semantics and limitations.
