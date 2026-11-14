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
6. **Health check** already exists: `GET /api/health`.

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

The trace already records every request, each LLM call (model, time, tokens, cost) and errors.
Minimum for the review: an admin-page panel (or a small
`/api/admin/metrics` endpoint) showing, for the last 24 h: requests, p50 / p95 latency per step,
error rate, LLM cost per search, and share of asks / emergency answers. Add one alert rule, e.g.
an e-mail if the error rate is above 10% in an hour (uptime check on `/api/health` with a free
service such as UptimeRobot).

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
- [ ] Monitoring panel + one alert rule
- [ ] Backup demo recording in case the network fails on 5 Dec
