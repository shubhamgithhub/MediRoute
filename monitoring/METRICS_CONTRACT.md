# MediRoute low-cost metrics contract

Status: implemented in source; AWS/dashboard deployment and live verification are manual.
Namespace: `MediRoute/Demo`. The only dimension is `Environment=dev`.
Seven unique series, standard resolution; no task/request/patient/model dimensions.

| Metric | Unit | Definition |
|---|---|---|
| Queries | Count | One terminal HTTP attempt on an included recommendation route |
| QueriesFailed | Count | One for HTTP 5xx, uncaught exception, cancellation or incomplete response; otherwise zero |
| QueriesRejected | Count | One for completed HTTP 4xx responses (including validation 422); otherwise zero |
| QueryTimeMs | Milliseconds | Raw nonnegative elapsed time through final response body, or failure |
| LLMCalls | Count | One per actual OpenRouter stream/network attempt, including retry/fallback attempts |
| LLMCostMissing | Count | One if that attempt has no valid provider-returned cost; otherwise zero |
| LLMCostUSD | None | Nonnegative finite provider-reported usage.cost; omitted when unavailable |

## Request scope

Only POST /api/patient-routing, /api/analyze, /api/hospitals/recommend and
/api/hospitals/semantic-recommendations count. Each clarification/follow-up submitted
by the client counts as another HTTP attempt. Internal graph nodes and provider
retries do not increment Queries. Health, static, admin, account and OPTIONS
requests are excluded. A clarification, emergency notice or no-match HTTP 200
counts as served successfully; this measures HTTP reliability, not clinical quality.
Server error rate = 100 * QueriesFailed / Queries. Rejections are shown separately.
No requests means no observation, not zero errors or 100% availability.

The ASGI middleware does not read, modify or buffer bodies. It measures through
the last response body, excluding post-response background work. Uncaught
exceptions/cancellation still propagate after one failure metric event. Abrupt
process termination or a lost log event may prevent an observation.

## LLM cost and limitations

The OpenRouter stream method is observed once per attempt, not once per streamed
chunk or per logical generate_json call. Repeated cumulative usage chunks are not
added together. A billed completion that produces invalid model JSON is still
recorded. An HTTP error or broken stream with no final usable usage is unknown,
even if the provider may have charged for work. No extra provider accounting
requests are made and no token prices are guessed.

Known daily USD is a partial total whenever missing-cost attempts exist.
The cost/query expression is only shown in windows with queries, LLM attempts,
no observed missing costs, and a reported cost sample for every call. A single
IF condition leaves incomplete windows absent (nested IF expressions can
turn a missing inner result into zero). It divides cost and query totals in the SAME hourly
window. This is an operational ratio, not per-patient billing: a parallel model
call can finish after its HTTP request, and long calls can cross a window boundary.
The cost-coverage chart exposes incomplete accounting. Windows with no LLM calls
are left blank, not labeled free. Provider data and EMF delivery are not a billing
ledger; reconcile against OpenRouter for actual spending.

LLM events cover this backend process. Do not enable the flag for unrelated
benchmark jobs that share the namespace/dimension. Local Ollama/disabled LLM
execution produces no OpenRouter cost events.

## Delivery, privacy and cost

The emitter is disabled by default; the ECS api container explicitly sets
MEDIROUTE_METRICS_ENABLED=true. Set it false and deploy a new task to disable
emission. The plain JSON EMF line goes to stdout, which the existing awslogs
driver sends to /ecs/mediroute-demo. Do not pass EMF through the normal prefixed
text logger: that would break extraction.

No extra application PutMetricData IAM permission, metric filter, SDK, collector,
agent or container is required. Existing execution-role log delivery must work.
Each event contains only the fixed dimension, metric names/numbers, and timestamp.
No prompts, responses, URLs, IDs, patient details or secrets are added. Existing
application diagnostic logs are outside this telemetry change and retain their
current behavior.

Telemetry output errors do not fail application requests. Emitters produce one
event per request/attempt; CloudWatch EMF delivery is at least once, so AWS-side
duplicates are possible. Small log volumes, fixed dimensions, and standard
resolution control cost. Extracted custom metrics/logs can incur AWS charges;
free allowances are account-wide, not guaranteed per project.

## Dashboard exclusions

Container Insights remains disabled: no CPU, memory or task-count metric widgets
are included. A text panel explicitly explains this limitation. No health probes,
Route 53 checks, Synthetics canaries, alarms, log-query widgets or scheduled jobs
are created. Uptime is not claimed. A future availability probe needs a separate
agreed demo window and must not treat intentional shutdown as downtime.

## Sources

- https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Embedded_Metric_Format.html
- https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Embedded_Metric_Format_Specification.html
- https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/using-metric-math.html
- https://openrouter.ai/docs/cookbook/administration/usage-accounting
