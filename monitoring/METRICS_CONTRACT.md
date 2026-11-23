# MediRoute low-cost metrics contract

Status: implemented in source; AWS/dashboard deployment and live verification are manual.
Namespace: `MediRoute/Demo`. The only dimension is `Environment=dev`.
Fourteen unique series at standard resolution. The single fixed dimension excludes task, request, patient, and model labels.

| Metric | Unit | Definition |
|---|---|---|
| Queries | Count | One terminal HTTP attempt on an included recommendation route |
| QueriesFailed | Count | One for HTTP 5xx, uncaught exception, cancellation or incomplete response; otherwise zero |
| QueriesRejected | Count | One for completed HTTP 4xx responses (including validation 422); otherwise zero |
| QueriesRetried | Count | One for a patient-routing POST marked by the browser Try again button after a timeout |
| QueryTimeMs | Milliseconds | Raw nonnegative elapsed time through final response body, or failure |
| LLMCalls | Count | One per actual OpenRouter stream/network attempt, including retry/fallback attempts |
| LLMCostMissing | Count | One if that attempt has no valid provider-returned cost; otherwise zero |
| LLMCostUSD | None | Nonnegative finite provider-reported usage.cost; omitted when unavailable |
| LLMCallTimeMs | Milliseconds | Wall time of one OpenRouter network attempt, including a failed attempt |
| LLMCallsFailed | Count | One when the network attempt raises an error, otherwise zero |
| LLMInputTokens | Count | Provider-reported prompt tokens when present |
| LLMOutputTokens | Count | Provider-reported completion tokens when present |
| ApiProbeSuccess | Count (0/1) | Direct API liveness probe returns the expected JSON |
| AppProbeSuccess | Count (0/1) | Direct API, patient HTML, and API through Nginx all pass |

## Request scope

Only POST /api/patient-routing, /api/analyze, /api/hospitals/recommend and
/api/hospitals/semantic-recommendations count. Each clarification/follow-up submitted
by the client counts as another HTTP attempt. Internal graph nodes and provider
retries do not increment Queries. The patient page sets a retry marker only
when the user chooses Try again after the 20-second timeout. Clarification
rounds and unmarked resubmissions do not count as retries. A browser retry
does not establish whether the earlier attempt failed server-side.
Health, static, admin, account and OPTIONS
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

The LLM panel also shows average and p95 response time per provider attempt
and separates provider-reported input and output tokens. Missing token fields
are omitted. Recorded token totals may be partial. Failed attempts refer to
transport or provider errors. A completed response that contains unusable
model JSON still counts as an observed provider response.

Known daily USD is a partial total whenever missing-cost attempts exist.
The cost/query expression is only shown in windows with queries, LLM attempts,
no observed missing costs, and a reported cost sample for every call. A single
IF condition leaves incomplete windows absent (nested IF expressions can
turn a missing inner result into zero). It divides the reported cost by recommendation attempts in the same UTC day. This is an operational ratio, not per-patient billing: a parallel model
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

## Application status

An API background thread checks direct API liveness, patient HTML served
by Nginx, and API liveness through Nginx over shared task loopback. It
waits about one minute for startup and runs about once a minute while the
API process is alive. The combined result requires all three checks.
The latest status cards show observations from the last five minutes.
A blank status means there was no recent observation, such as during a
planned stop. The checks do not exercise recommendations, provider
availability, public DNS or TLS. The DuckDNS deployment workflow checks
public HTTPS separately at deployment time.

The dashboard uses request traffic, server errors and latency from SRE
monitoring guidance. Average, p50 and p95 use per-attempt observations.
LLM instrumentation follows the OpenTelemetry client duration and separate
input/output token conventions, represented as existing CloudWatch metrics.
Container Insights stays disabled. No paid canary, scheduled external probe,
alarm, or resource saturation dashboard is provisioned.

## Sources

- https://sre.google/sre-book/monitoring-distributed-systems/
- https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-metrics/

- https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Embedded_Metric_Format.html
- https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Embedded_Metric_Format_Specification.html
- https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/using-metric-math.html
- https://openrouter.ai/docs/cookbook/administration/usage-accounting
