# Docker Guide

How this backend is packaged into a container, how to build and run it locally, and how that same image ends up running on GCP. Written as a companion to `DATABASE_MIGRATIONS_GUIDE.md` — read that one first if you haven't.

---

## 1. The core concept

Docker has two ideas everything else builds on:

- **Image** — a frozen, read-only snapshot: a packaged-up filesystem containing Python, your dependencies, and your code, built from the instructions in `Dockerfile`. Think of it like a `.zip` of an entire tiny computer, ready to run anywhere.
- **Container** — a live, running instance of that image. You can start and stop many containers from the same image; each one starts fresh from that frozen snapshot every time.

This split is what solves "works on my machine": the image is identical everywhere — your laptop, GCP, a teammate's machine — so if it runs correctly as a container locally, it runs the same way on Cloud Run later. No more subtle Python-version or missing-system-library differences between environments.

---

## 2. What's in this repo

| File | Purpose |
|---|---|
| `Dockerfile` | Instructions for building the image — base OS/Python version, dependency install, how the app starts. |
| `.dockerignore` | Files that must **never** be copied into the image (secrets, local venv, `.git`, scratch DBs). Same idea as `.gitignore`, but for the Docker build. |

### Walking through the Dockerfile

- `FROM python:3.13-slim` — a minimal Linux image with Python pre-installed, version-matched to the local dev venv so behavior doesn't quietly differ between your machine and the container.
- `ENV PYTHONDONTWRITEBYTECODE=1` / `PYTHONUNBUFFERED=1` — skip writing `.pyc` files (pointless in a container rebuilt from scratch each time) and disable output buffering, so log lines appear immediately in GCP's logs instead of potentially being lost if the container crashes mid-buffer.
- `COPY requirements.txt .` followed by `RUN pip install ...` happens **before** `COPY . .` (the rest of the code). Docker caches each instruction as a layer and reuses a cached layer if nothing above it changed. `requirements.txt` changes rarely; application code changes constantly — so this ordering means most rebuilds skip re-downloading every dependency and only redo the fast "copy code" step.
- The `CMD` at the bottom is what runs when the container starts: `gunicorn` (production process manager, restarts a worker if it crashes) running `uvicorn` workers (the actual async server FastAPI needs), bound to whatever port is given via the `$PORT` environment variable. **Cloud Run sets `$PORT` itself and expects the container to listen on it — never hardcode a port.**

### Why `.dockerignore` matters

Anything listed in `.dockerignore` never enters the Docker build process at all, not even temporarily. This repo excludes:
- `myenv/`, `__pycache__/`, `*.pyc` — local virtualenv and bytecode; the image installs fresh dependencies instead.
- `app/.env`, `app/firebase-key.json`, `*.env` — **secrets must never be baked into an image.** Anyone who can pull an image can read every file inside it, including old layers — so a secret baked in at some point stays retrievable even after being "removed" in a later layer. These get delivered to the running container separately instead (see §5).
- `*.db` — local SQLite scratch databases, not the real production database (that's Cloud SQL, reached via `DATABASE_URL`).
- `.git/`, `.gitignore`, `.DS_Store` — irrelevant inside the container.
- `scripts/`, `tests/` — not needed at runtime.

---

## 3. Building and running locally, step by step

**Step 0 — install Docker.** Docker Desktop for Mac (docker.com), open it, wait for the whale icon in the menu bar to go steady/ready.

**Step 1 — build the image:**
```bash
cd ~/Desktop/expos/pos-backend
docker build -t pos-backend .
```
Docker reads the `Dockerfile` top to bottom and executes each instruction, printing progress as it pulls the base image, installs `requirements.txt`, and copies the code in. `-t pos-backend` names ("tags") the resulting image so it can be referred to later instead of a random ID. The trailing `.` sets the *build context* — the set of files Docker is allowed to look at — to the current directory, which is exactly why `.dockerignore` matters.

First build: a few minutes (downloading the base image, installing every package). Every build after that is much faster thanks to layer caching, as long as `requirements.txt` hasn't changed.

**Step 2 — run a container from that image:**
```bash
docker run -p 8080:8080 --env-file app/.env pos-backend
```
- `docker run` starts a new container from the `pos-backend` image.
- `-p 8080:8080` connects a port on the Mac to a port inside the container. Without this, the container is its own isolated machine — a server running on its internal port 8080 would be completely unreachable from outside. This says "traffic hitting `localhost:8080` on my Mac forwards to port 8080 inside the container."
- `--env-file app/.env` loads environment variables (`DATABASE_URL`, `ADMIN_API_TOKEN`, etc.) into the container's environment — none of this is baked into the image itself (see §2 on `.dockerignore`).

**Step 3 — verify it works:** open `http://localhost:8080/docs` — if Swagger loads and an endpoint responds, the containerized app is working. This is the proof the image is genuinely portable: if it works here, it'll work identically when GCP runs the exact same image later.

---

## 4. The `localhost` database gotcha

`DATABASE_URL` in `app/.env` almost certainly points at `localhost:5432` (Postgres running directly on the Mac). **`localhost` inside a container refers to the container itself, not the host Mac.** So the containerized app, using that same `.env`, will fail to connect to local Postgres — not a bug in the setup, just a Docker networking reality.

**Fix for local testing only:**
```bash
docker run -p 8080:8080 --add-host=host.docker.internal:host-gateway --env-file app/.env.docker pos-backend
```
using a copy of `.env` (`app/.env.docker`) with `localhost` replaced by `host.docker.internal` in `DATABASE_URL`.

This issue disappears entirely once actually on GCP — Cloud Run and Cloud SQL talk over GCP's internal network, not `localhost`, so this is purely a local-testing quirk, not something to solve for production.

---

## 5. How this fits the GCP journey

1. Build the image locally and confirm it runs (§3 above).
2. Push that same image to **Artifact Registry** (GCP's Docker image storage). Typically one step: `gcloud builds submit` (builds *and* pushes using Google's build infrastructure) or `docker push` after tagging for the registry.
3. Point **Cloud Run** at that image and deploy — Cloud Run pulls the image and starts containers from it based on traffic, giving a public HTTPS URL.
4. Cloud Run injects `$PORT`, environment variables, and mounted secrets into each container it starts — the exact same mechanism as `docker run -p` and `--env-file` used locally, just orchestrated by GCP instead of typed by hand.

**The image and startup command are identical the whole way through.** Getting it working locally is not a detour from the GCP setup — it *is* the GCP setup, minus the "how do I get this image there and tell Cloud Run how to talk to it" part, which is what the GCP-specific topics (Cloud SQL, secrets, Cloud Run deploy) cover next.

**Run migrations before the first deploy.** `app/main.py` no longer calls `Base.metadata.create_all()` (removed 2026-08-14 — see `DATABASE_MIGRATIONS_GUIDE.md`), so a brand-new Cloud SQL database has zero tables until you run `alembic upgrade head` against it. Do this once against the target database before pointing Cloud Run at it for the first time — the app will fail on every request (not just start up oddly) if the schema doesn't exist yet.

---

## 6. Secrets — the one real gap, revisited

`app/firebase-key.json` and `app/.env` are correctly excluded from the image. That means the running container needs those values delivered another way at deploy time:
- Simple values (`DATABASE_URL`, `ADMIN_API_TOKEN`, `RAZORPAY_MODE`, `RAZORPAY_LIVE_KEY_SECRET`, `EMAIL_ADDRESS`, `EMAIL_PASSWORD`, etc.) → stored in **Secret Manager**, injected as env vars via `--set-secrets` on deploy. See `app/services/razorpay_service.py`'s module docstring for the full Razorpay test/live variable set and how `RAZORPAY_MODE` picks between them.
- `firebase-key.json` (a whole file, not a single value) → also Secret Manager, but mounted as a **file**, not an env var.

### The Secret Manager file-mount gotcha (found the hard way, 2026-08-15)

`app/firebase_service.py` reads its credentials path from `FIREBASE_KEY_PATH` (falls back to the original `app/firebase-key.json` for local dev when unset). **Do not mount the file-based secret anywhere under `app/`.**

Cloud Run mounts a secret *file* by creating a volume at that file's **parent directory** — not just placing the one file there. Mounting to `/app/app/firebase-key.json` doesn't add a file into your existing `app/app/` directory; it replaces the entire directory with a fresh, empty-except-for-this-one-file volume, silently wiping out `main.py`, `routes/`, everything else that lives there. The container then fails to boot with a confusing `ModuleNotFoundError: No module named 'app.main'` that has nothing obviously to do with the secret you just added.

**The fix:** mount the file secret somewhere that doesn't collide with your code, e.g. `/secrets/firebase-key.json`, and set `FIREBASE_KEY_PATH=/secrets/firebase-key.json` alongside it. Both go on the same `gcloud run deploy` command — see the file-mount syntax in §7 below (`PATH=SECRET_NAME:VERSION`, distinguished from env-var secrets by the `/` in the left-hand side).

---

## 7. A real deploy, start to finish (Cloud Run + Cloud SQL + Secret Manager)

This is the actual sequence that got a working test deployment live, including the mistakes worth not repeating.

**Prerequisites:** Docker Desktop running, `gcloud` CLI authenticated as the account that owns the project (`gcloud auth login`, then `gcloud config set project YOUR_PROJECT`), Artifact Registry API + Secret Manager API enabled.

**1. Create the Cloud SQL instance** (Console → SQL → Create Instance → PostgreSQL), or `gcloud sql instances create`. Note the instance connection name (`project:region:instance-name`) and the database password.

**2. Apply migrations before anything else can work** — via the Cloud SQL Auth Proxy, not a public connection:
```bash
./cloud-sql-proxy --port 5433 PROJECT:REGION:INSTANCE
# in a second terminal:
export DATABASE_URL="postgresql://postgres:PASSWORD@127.0.0.1:5433/DBNAME"
alembic upgrade head
```
(Port 5433, not 5432 — avoids colliding with a local Postgres server already listening on 5432.)

**3. Push the image to Artifact Registry.** Build with `--platform linux/amd64` explicitly if you're on Apple Silicon — Cloud Run only runs `linux/amd64` images, and a Mac's native Docker build defaults to `arm64`, which fails with a cryptic "must support amd64/linux" manifest error otherwise:
```bash
gcloud artifacts repositories create REPO_NAME --repository-format=docker --location=REGION
gcloud auth configure-docker REGION-docker.pkg.dev
docker build --platform linux/amd64 -t REGION-docker.pkg.dev/PROJECT/REPO_NAME/pos-backend:TAG .
docker push REGION-docker.pkg.dev/PROJECT/REPO_NAME/pos-backend:TAG
```

**4. Create every secret in Secret Manager**, one per sensitive value (`DATABASE_URL`, `JWT_SECRET_KEY`, `ADMIN_API_TOKEN`, `RAZORPAY_TEST_KEY_ID`/`KEY_SECRET`/`WEBHOOK_SECRET`, `EMAIL_ADDRESS`, `EMAIL_PASSWORD`), plus the Firebase key as a file-backed secret:
```bash
echo -n "VALUE" | gcloud secrets create SECRET_NAME --data-file=-
gcloud secrets create FIREBASE_KEY --data-file=app/firebase-key.json
```
Then grant Cloud Run's service account read access to each one (find the account via `gcloud iam service-accounts list`):
```bash
gcloud secrets add-iam-policy-binding SECRET_NAME \
  --member="serviceAccount:PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

**5. Deploy**, wiring env-var secrets and the file-mount secret together (note the different syntax — `NAME=SECRET:latest` for env vars, `PATH=SECRET:latest` for a file, distinguished by the `/`):
```bash
gcloud run deploy SERVICE_NAME \
  --image=REGION-docker.pkg.dev/PROJECT/REPO_NAME/pos-backend:TAG \
  --region=REGION \
  --add-cloudsql-instances=PROJECT:REGION:INSTANCE \
  --min-instances=0 --max-instances=2 --cpu=1 --memory=512Mi \
  --allow-unauthenticated \
  --set-env-vars=RAZORPAY_MODE=test,FIREBASE_KEY_PATH=/secrets/firebase-key.json \
  --set-secrets=DATABASE_URL=DATABASE_URL:latest,JWT_SECRET_KEY=JWT_SECRET_KEY:latest,ADMIN_API_TOKEN=ADMIN_API_TOKEN:latest,RAZORPAY_TEST_KEY_ID=RAZORPAY_TEST_KEY_ID:latest,RAZORPAY_TEST_KEY_SECRET=RAZORPAY_TEST_KEY_SECRET:latest,RAZORPAY_TEST_WEBHOOK_SECRET=RAZORPAY_TEST_WEBHOOK_SECRET:latest,EMAIL_ADDRESS=EMAIL_ADDRESS:latest,EMAIL_PASSWORD=EMAIL_PASSWORD:latest,/secrets/firebase-key.json=FIREBASE_KEY:latest
```
`DATABASE_URL` for the Cloud Run Unix-socket connection method looks like:
```
postgresql://postgres:PASSWORD@/DBNAME?host=/cloudsql/PROJECT:REGION:INSTANCE
```
(No host/port before the `?` — that's correct, it's a Unix socket, not a TCP connection.)

**6. Verify:**
```bash
curl https://YOUR-SERVICE-URL.a.run.app/health
```
If this fails, `gcloud run services logs read SERVICE_NAME --region=REGION --limit=100` will show a Python traceback pointing at whatever's missing — every env var this app touches at *import time* (not just when a route is called) will crash the whole container on boot, not just that one feature. `EMAIL_ADDRESS`/`EMAIL_PASSWORD` and the Firebase credentials are both imported eagerly this way, which is why they surfaced as boot failures rather than only breaking their specific endpoints.

### Schema drift check

Before (and after) any deploy against a new database, run:
```bash
export DATABASE_URL="..."  # via the Cloud SQL proxy, same as step 2
python3 scripts/check_schema_drift.py
```
This compares every SQLAlchemy model's columns against what's actually in the connected database and reports any mismatch. It exists because `StoreGstProfile.address` was defined on the model with no matching migration for a long time — invisible on any database that had ever been touched by the old `Base.metadata.create_all()` behavior (removed 2026-08-14), and only surfaced as a live `UndefinedColumn` production error on the first database built strictly from `alembic upgrade head`. Run it against any freshly-migrated database before trusting it.

---

## 8. Custom domain (Load Balancer, not Cloud Run domain mappings)

Cloud Run's built-in "domain mappings" feature is Preview-only, not GA, and has known latency/reliability caveats — not something to rely on for a real deployment, and not reliably available in every region (e.g. `asia-south1`). Use an External HTTPS Load Balancer with a Serverless NEG instead — more setup, but GA and works in any region.

1. Reserve a static global IP: `gcloud compute addresses create NAME --global`
2. Create a Serverless NEG pointing at the Cloud Run service: `gcloud compute network-endpoint-groups create NAME --region=REGION --network-endpoint-type=serverless --cloud-run-service=SERVICE_NAME`
3. Create a backend service and attach the NEG to it (`gcloud compute backend-services create` + `add-backend`).
4. Create a URL map pointing at that backend service (`gcloud compute url-maps create`).
5. Create a Google-managed SSL cert for the domain (`gcloud compute ssl-certificates create --domains=...`) — stays in `PROVISIONING` until DNS is correctly pointed AND Google's system detects it, which can take anywhere from 15 minutes to a couple of hours even once DNS is correct.
6. Create the HTTPS target proxy referencing the cert + URL map.
7. Create a forwarding rule binding the static IP to the HTTPS proxy on port 443.
8. Add an **A record** (not CNAME) at the registrar pointing the subdomain at the static IP from step 1.

If the cert seems stuck in `PROVISIONING` for an unusually long time, check for a CAA DNS record restricting which certificate authorities are allowed to issue for the domain (`dig DOMAIN CAA +short`) — an empty result means no restriction; anything else needs to explicitly permit Google's CA.
