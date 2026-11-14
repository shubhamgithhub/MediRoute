# Cloud deployment guide (draft)

Owner: Aniket (tracker rows 29 Docker, 30 CI, 46 cloud deployment, 47 monitoring). Draft, 14 Nov 2026.
Goal: one public HTTPS URL for the final review (5 Dec) and the outside-user test (row 54), running
the same code and data as the local app.

---

## 1. What the app is today

| Part | How it runs locally | Notes for the cloud |
|---|---|---|
| Backend API | `uvicorn mediroute.backend.main:app` on `127.0.0.1:8000` | FastAPI; Step 1 + Step 2 + admin API |
| Frontend | `python scripts/serve_frontend.py` on `:5500` | Plain HTML/CSS/JS in `frontend/` (no build step) |
| LLM | OpenRouter, GPT-6 Luna (`OPENROUTER_API_KEY`) | Hosted: nothing to install. Ollama is **not** needed in the cloud |
| Embedding models | `all-MiniLM-L6-v2`, `multi-qa-MiniLM-L6-cos-v1` (Hugging Face, ~90 MB each) | Downloaded on first use: **bake into the image** so start-up needs no download |
| Data | `data/processed/` (19 MB: hospitals.csv, specialties.csv, specialty_mapping.csv, body-area files, step1_lookup.csv, FAISS index + embedding caches) | Committed in git; copy into the image |
| Trace / admin history | `logs/step1_trace.jsonl`, pruned to the newest 100 requests | Needs a **persistent disk** if the admin history should survive restarts |
| Memory | Backend ≈ 2.2 GB (torch + two MiniLM models + FAISS) | Machine with **≥ 4 GB RAM** |

**One Docker image, not two.** The frontend is static HTML/CSS/JS with no build step, so FastAPI serves
it next to the API: one container, one URL, no CORS, one version tag per git commit. Caddy (HTTPS) runs
on the VM or as an off-the-shelf container; it is not an image we build. Two images only make sense if
the frontend moves to static hosting (S3/CDN) or several backend copies run behind a load balancer.

## 2. Code changes needed before deploying (small)

1. **API address in the frontend is hard-coded** to `http://127.0.0.1:8000`
   (`frontend/js/patient.js` line 5, `frontend/js/admin.js` line 5). Change to a relative address
   (`""` / `"/api/..."`) so the page calls the server it was loaded from.
2. **Serve the frontend from FastAPI** (one container, one URL, no CORS): mount `frontend/` with
   `StaticFiles` at `/` in `backend/main.py`, after the API routers.
3. **CORS** (`backend/main.py`) only allows `localhost:5500`. Not needed after step 2; otherwise add
   the public domain.
4. **Protect the admin page.** `admin.html` and `/api/admin/*` have **no login** today and show
   patient text. Minimum: HTTP basic auth (username/password from environment variables) on
   `/admin.html` and `/api/admin/*`. This is also tracker row 56.
5. **Listen on all interfaces** in the container: `--host 0.0.0.0` (or `MEDIROUTE_HOST=0.0.0.0`).
6. **Health check** exists (`GET /api/health`) but only says the server is up; section 8.1 makes it
   check the indexes and the LLM, and adds one summary log line per request for monitoring.

## 3. Settings (environment variables)

| Variable | Cloud value | Why |
|---|---|---|
| `OPENROUTER_API_KEY` | project key (secret store, never in git) | LLM calls |
| `MEDIROUTE_OPENROUTER_MODEL` | `openai/gpt-6-luna` | Same model as the benchmarks |
| `MEDIROUTE_LLM_PROVIDER` | `openrouter` | Explicit (default when the key is set) |
| `MEDIROUTE_JUDGE_MODEL` | `openai/gpt-6-luna` | Judge model |
| `MEDIROUTE_LLM_TIMEOUT_S` | `20` | Matches the 20 s patient-page timeout |
| `MEDIROUTE_LOG_DIR` | `/data/logs` (persistent disk) | Admin history survives restarts |
| `MEDIROUTE_TRACE_KEEP` | `100` | Retention: newest 100 requests only (DPDP) |
| `MEDIROUTE_LOG_PATIENT_TEXT` | `1` for the demo, `0` for outside users if consent is not collected | Patient text in the trace |
| `ADMIN_USER`, `ADMIN_PASSWORD` | secret | Admin login (change 4) |

OpenRouter: new accounts allow ~20 requests/minute per model. One search makes 2–4 LLM calls, so
a demo with several people at once needs credits on the account (higher limit) and a **spend
cap** set in the OpenRouter dashboard. Cost so far: about $0.0004 per search.

## 4. Docker image (row 29)

```dockerfile
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app/src HF_HOME=/app/hf_cache
# CPU-only torch keeps the image ~1.5 GB smaller
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
# bake the two embedding models into the image (no download at start-up)
RUN python -c "from sentence_transformers import SentenceTransformer as S; S('sentence-transformers/all-MiniLM-L6-v2'); S('sentence-transformers/multi-qa-MiniLM-L6-cos-v1')"
COPY data/processed ./data/processed
COPY frontend ./frontend
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
CMD ["uvicorn", "mediroute.backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

- Use **Python 3.12** in the image (local machines run 3.14; faiss-cpu and torch wheels are safest
  on 3.12). Run the test suite inside the image once: `docker run --rm <image> python -m pytest -q`.
- `--workers 1`: each worker loads the models (~2 GB); one worker is enough for a demo.
- Add a `.dockerignore`: `.venv`, `logs`, `data/evaluation`, `data/raw`, `archive`, `docs/report`,
  `.git`, `__pycache__`.
- `docker-compose.yml` for local runs: one service, port 8000, an `.env` file, a volume for `/data/logs`.

## 5. Where to host (choose one)

| Option | RAM / cost | Pros | Cons | Fit |
|---|---|---|---|---|
| **A. One small VM** (AWS EC2 t3.medium, GCP e2-medium, Azure B2s) + Docker + Caddy for HTTPS | 4 GB · about ₹2,500–3,500 / month | Always on, no cold start, persistent disk for logs, simple to explain | You patch the VM; set up HTTPS yourself (Caddy does it automatically with a domain) | **Recommended** |
| B. Google Cloud Run (container service) | 4 GB, pay per request · near ₹0 idle | HTTPS + scaling built in, deploy from the image | Cold start loads models (~20–40 s first request); disk is not persistent (admin history lost) unless logs go to Cloud Storage | Good if cost matters more |
| C. Hugging Face Spaces (Docker) | 16 GB free CPU | Free, easy, HTTPS | Public by default, sleeps when idle, less "production-like" than a VM | Backup demo |
| D. Render / Railway | 4 GB plans ~US$25+/month | Git push to deploy | Free tiers have too little RAM (512 MB–1 GB) | Possible |

Estimate: option A for 1 month ≈ ₹3,000 plus LLM calls (< ₹500 for the demo period).

## 6. Steps (option A)

1. Make the code changes in section 2; run tests; build and run the image locally
   (`docker compose up`), open `http://localhost:8000/patient.html`, run three test searches.
2. Create the VM (Ubuntu 22.04, 2 vCPU, 4 GB RAM, 30 GB disk); open ports 80 and 443 only.
3. Install Docker; copy the image (push to Docker Hub / GitHub Container Registry, then `docker pull`).
4. Put secrets in `/opt/mediroute/.env` (readable by root only); create `/opt/mediroute/logs`.
5. `docker run -d --restart unless-stopped --env-file /opt/mediroute/.env -v /opt/mediroute/logs:/data/logs -p 127.0.0.1:8000:8000 <image>`
6. Point a domain (or a free subdomain, e.g. DuckDNS) at the VM; install Caddy with
   `reverse_proxy 127.0.0.1:8000` → automatic HTTPS.
7. Smoke test from outside: patient page, a report upload, the admin page asks for the password,
   `/api/health` returns healthy. Run `scripts/api_smoke_workflow.py` against the public URL.
8. Write the URL, version (git commit) and date into the README and the report.

## 7. CI and updates (rows 30, 48)

- GitHub Actions on every push: `ruff` + `pytest`; on `main`: build the image and push it to
  GitHub Container Registry tagged with the commit.
- Optional eval gate (row 48): a small Step 1 set (e.g. core50 with cached LLM answers) that fails
  the build if confidently-wrong rises.
- Update the VM: `docker pull` the new tag and restart; keep the previous tag to roll back.

## 8. Monitoring (row 47)

What we measure: uptime, health, queries per hour / day, failed queries, time per query, LLM cost
per day / per query, error rate. AWS needs no "sidecar": the app writes **one JSON line per request**
to its console log, Docker ships the console log to **CloudWatch Logs**, and CloudWatch turns those
lines into metrics, a dashboard and alarms. Uptime comes from an outside check of `/api/health`.

```
patient --HTTPS--> Caddy --> MediRoute container --stdout--> Docker awslogs driver --> CloudWatch Logs
                                   ^                                                      | metric filters
   Route 53 health check ----------+ GET /api/health every 30 s                           v
            |                                                               CloudWatch metrics --> Dashboard
            +------------------------> HealthCheckStatus metric ---------------------------> Alarms --> SNS e-mail
```

### 8.1 API changes (two, small; about 1.5 h with tests)

Both help on any host (AWS, GCP, a laptop); only the CloudWatch setup in 8.2 is AWS-specific.

**Change 1: one summary line per request (`request_done`).** At the end of `/api/patient-routing`
(patient page) and `/api/analyze` (Step 1 only), success or failure, the app logs one JSON line to
the console and `mediroute.log`:

```json
{"event": "request_done", "ts": "2026-12-01T10:15:02Z", "endpoint": "/api/patient-routing",
 "workflow_id": "b4bc004925e5", "status": "completed", "http_status": 200,
 "step1_decision": "agreement", "specialty": "Reproductive Medicine", "emergency": false,
 "asked": false, "hospitals": 5, "related_specialty": "Obstetrics & Gynaecology",
 "reports": 0, "ms": 5450, "step1_ms": 5166, "step2_ms": 263,
 "llm_calls": 2, "llm_failed": 0, "llm_cost_usd": 0.00041, "model": "openai/gpt-6-luna",
 "error": null}
```

- `status`: `completed`, `clarification` (asked a question), `no_hospital`, `emergency`, `failed`.
- `llm_cost_usd`: sum of the cost OpenRouter returns for each LLM call of the request (already in the trace).
- **No patient text, city or report content** in this line, so the CloudWatch logs hold no health data.
- Written in a `finally` block, so a crash still produces a line with `status: "failed"` and the error type.

**Change 2: a real health check.** `GET /api/health` keeps today's fields (`status`, `service`) and
adds checks:

```json
{"status": "healthy", "service": "MediRoute API", "version": "922d5a1", "uptime_s": 86400,
 "checks": {"indexes": "ok", "llm": "ok", "log_dir": "ok"}}
```

| State | When | HTTP |
|---|---|---|
| `healthy` | indexes loaded, the last LLM call in the past 10 min worked (or none yet), log folder writable | 200 |
| `degraded` | LLM unreachable or key missing: the app still answers with the lookup only | 200 |
| `unhealthy` | indexes / data failed to load: the app cannot answer | 503 |

- The health check **does not call the LLM** (a call every 30 s would cost money and use the
  20 requests/minute limit); it reads the result of the most recent real LLM call.
- `degraded` returns 200 on purpose, so a short OpenRouter outage is not counted as downtime; it shows
  up in the LLM-failure metric instead.
- `version` = git commit, set at image build (`--build-arg GIT_COMMIT=...` -> env `MEDIROUTE_VERSION`).

**Effect on the admin page: none.** The admin history reads `logs/step1_trace.jsonl`; the summary line
goes only to the console / app log, and nothing in the trace is renamed or removed. The frontend does
not call `/api/health`; the two scripts that do (`portal_benchmark.py`, `verify_specialty_route.py`)
only need `status` and HTTP 200, which stay. To verify: the full test suite plus new tests for the
summary line and the three health states, and one live search checked on the admin page.

### 8.2 CloudWatch setup on EC2

1. **IAM role for the EC2 instance** with `logs:CreateLogGroup`, `logs:CreateLogStream`,
   `logs:PutLogEvents` (or the managed policy `CloudWatchAgentServerPolicy`). No access keys on the VM.
2. **Send the container log to CloudWatch** with Docker's built-in `awslogs` driver (add to the
   `docker run` in section 6, step 5):
   ```
   --log-driver awslogs --log-opt awslogs-region=ap-south-1 \
   --log-opt awslogs-group=/mediroute/app --log-opt awslogs-create-group=true
   ```
   Set the log group's retention to **30 days**.
3. **Metric filters** on `/mediroute/app` (namespace `MediRoute`):

   | Metric | Filter pattern | Value | Unit |
   |---|---|---|---|
   | `Requests` | `{ $.event = "request_done" }` | 1 | Count |
   | `FailedRequests` | `{ $.event = "request_done" && $.status = "failed" }` | 1 | Count |
   | `LatencyMs` | `{ $.event = "request_done" }` | `$.ms` | Milliseconds |
   | `LlmCostUsd` | `{ $.event = "request_done" }` | `$.llm_cost_usd` | None |
   | `LlmFailedCalls` | `{ $.event = "request_done" && $.llm_failed > 0 }` | `$.llm_failed` | Count |
   | `EmergencyAnswers` | `{ $.event = "request_done" && $.emergency IS TRUE }` | 1 | Count |
   | `Asked` | `{ $.event = "request_done" && $.status = "clarification" }` | 1 | Count |

4. **Uptime / health**: a **Route 53 health check** on `https://<domain>/api/health` (HTTPS, every
   30 s, from several regions; healthy = HTTP 2xx/3xx). Its `HealthCheckStatus` (1 = up) and
   `HealthCheckPercentageHealthy` metrics are published in **us-east-1** only, so build the dashboard
   there or add a cross-region widget. Also keep the EC2 `StatusCheckFailed` metric (machine down).
   Memory and disk are not EC2 metrics by default: install the **CloudWatch agent** for
   `mem_used_percent` and `disk_used_percent` (the app needs about 2.2 GB of 4 GB).
5. **Dashboard `MediRoute`** (period 1 h for the day view, 1 day for the week view):

   | Widget | What | Statistic / maths |
   |---|---|---|
   | Uptime | `HealthCheckPercentageHealthy` | Average, last 24 h and 7 days |
   | Health now | `HealthCheckStatus` | Minimum, 1 min (number widget) |
   | Queries per hour / per day | `Requests` | Sum, period 1 h / 1 d |
   | Failed queries | `FailedRequests` | Sum, period 1 h / 1 d |
   | Error rate % | `100 * FailedRequests / Requests` | metric maths on Sums |
   | Time per query | `LatencyMs` | p50, p95, maximum |
   | LLM cost per day | `LlmCostUsd` | Sum, period 1 d |
   | LLM cost per query | `LlmCostUsd / Requests` | metric maths on Sums |
   | LLM failures | `LlmFailedCalls` | Sum, 1 h |
   | Asks / emergencies | `Asked`, `EmergencyAnswers` | Sum, 1 d |
   | Machine | `CPUUtilization`, `mem_used_percent`, `disk_used_percent` | Average |
   | Recent failures | Logs Insights query (below) | table |

   Logs Insights query for the "Recent failures" widget:
   ```
   filter event = "request_done" and status = "failed"
   | fields ts, workflow_id, endpoint, error
   | sort ts desc
   | limit 20
   ```

6. **Alarms -> SNS topic `mediroute-alerts` (e-mail to the team)**:

   | Alarm | Condition |
   |---|---|
   | Site down | `HealthCheckStatus` < 1 for 2 of 2 minutes (in us-east-1) |
   | Error rate high | error rate > 10% over 1 h with at least 5 requests |
   | Slow | `LatencyMs` p95 > 20 000 ms over 15 min (the patient-page timeout) |
   | LLM failing | `LlmFailedCalls` >= 5 in 15 min |
   | Spend | `LlmCostUsd` Sum > US$1 per day (also keep the OpenRouter spend cap) |
   | Machine | `StatusCheckFailed` >= 1, or `mem_used_percent` > 90% for 10 min |

7. **Test the setup**: run `scripts/api_smoke_workflow.py` against the public URL; check the lines in
   Logs Insights and the dashboard counts; stop the container for 2 minutes and check that the
   "site down" e-mail arrives.

**Cost** (demo traffic, a few hundred requests a day): logs well under 1 GB a month, 7 custom
metrics, one dashboard, about 8 alarms and one health check: roughly **US$5 a month or less**
(check current CloudWatch / Route 53 prices before setting up).

**Not on AWS?** The same JSON line works with GCP Cloud Logging (log-based metrics) or any log tool;
UptimeRobot (free) can check `/api/health` instead of Route 53.

## 9. Safety, privacy and wording (TA feedback)

- Uploaded PDFs are read in memory and **not stored**; keep it that way (no upload folder in the image).
- Trace retention: newest 100 requests (`MEDIROUTE_TRACE_KEEP`); admin page behind a password.
- For outside users: a one-line consent note on the patient page ("don't upload real reports with
  your name; test data only"), matching the privacy note (row 36).
- Keep the disclaimers and the academic notice on every page; never name any similar live service.

## 10. Checklist

- [ ] Frontend uses relative API URLs; FastAPI serves `frontend/`
- [ ] Admin page and admin API protected by a password
- [ ] Dockerfile + `.dockerignore` + `docker-compose.yml`; tests pass inside the image
- [ ] OpenRouter project key with a spend cap, stored as a secret
- [ ] VM (or Cloud Run) running with HTTPS and a persistent log disk
- [ ] Smoke test from outside passes; URL in README and report
- [ ] CI: tests on push, image on `main`
- [ ] API changes 8.1 (summary line per request, health checks) merged with tests
- [ ] CloudWatch: log group, metric filters, Route 53 health check, dashboard, alarms to e-mail (8.2)
- [ ] Backup demo recording in case the network fails on 5 Dec
