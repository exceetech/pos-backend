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
- Simple values (`DATABASE_URL`, `ADMIN_API_TOKEN`, `RAZORPAY_MODE`, `RAZORPAY_LIVE_KEY_SECRET`, etc.) → environment variables set directly in the Cloud Run service config. See `app/services/razorpay_service.py`'s module docstring for the full Razorpay test/live variable set and how `RAZORPAY_MODE` picks between them.
- `firebase-key.json` (a whole file, not a single value) → **Secret Manager**, mounted as a file at a path Cloud Run is told to use.

The code currently does `credentials.Certificate("app/firebase-key.json")` (`app/firebase_service.py`) — assumes a literal file at that exact path, so whatever mounts the secret on Cloud Run needs to put it there. This is covered in more detail when Cloud Run deployment is set up.
