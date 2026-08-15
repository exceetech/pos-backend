# Redeploy Guide — Pushing a Local Code Change to Cloud Run

This is the step-by-step for the everyday case: you changed something in the backend code on your laptop, and now need that change running live on Cloud Run. Companion to `GCP_SETUP_COMPLETE_GUIDE.md`, which covers the one-time setup that makes this possible — this document only covers the repeatable cycle, in full detail, explaining what each step does and why it exists.

---

## The short version

1. Test locally.
2. If the database changed, write and test the migration locally.
3. Rebuild the Docker image.
4. Push the image to Artifact Registry.
5. If the database changed, apply the migration to the cloud database.
6. Redeploy Cloud Run with the new image.
7. Verify.
8. Check logs.

The rest of this document walks through each of these in full, with the reasoning behind them.

---

## Step 1 — Test locally first

Make the code change, then run and test the app the normal way, against the local database on your own machine.

**Why this matters:** every step after this one adds a layer of distance between you and the actual bug, if there is one. If something's broken, you want to find that out while it's still just "a bug in my code," not "a bug in my code that's also tangled up with a deployment problem." Confirming it works locally first means that if something goes wrong later in this guide, you already know it's a deployment issue, not a code issue — cutting the number of possible causes in half before you even start debugging.

---

## Step 2 — If the database changed, handle the migration locally first

If this code change added, removed, or altered a database table or column, there will be a new file in `migrations/versions/` (an Alembic migration). Before touching the cloud database at all:

```bash
alembic upgrade head
```

Run this against your **local** database, and confirm the app still works correctly against the new schema.

**Why this matters:** the cloud database (`scalancer-pos-db`) holds real test data you've been building up — it's not something to experiment on directly. Proving the migration works locally first means that when it's later applied to the cloud database (Step 5), it's a known-good operation, not a live experiment. If this step is skipped and a migration turns out to be wrong, fixing it on the cloud database is much more annoying than fixing it locally where mistakes cost nothing.

**If nothing about the database changed**, skip this step entirely — most day-to-day fixes (a UI bug, a logic error, a new field validation) don't touch the database at all.

---

## Step 3 — Rebuild the Docker image

```bash
cd ~/Desktop/expos/pos-backend
docker build --platform linux/amd64 -t asia-south1-docker.pkg.dev/scalancer-pos-prod/scalancer-repo/pos-backend:test .
```

**Before running this:** make sure Docker Desktop is actually open (check for the whale icon in the Mac menu bar) — the build fails immediately with a "cannot connect to the Docker daemon" error otherwise.

**What this command does, piece by piece:**
- `docker build` — reads the `Dockerfile` and follows its instructions to assemble a fresh image: install dependencies, copy in the current code.
- `--platform linux/amd64` — **this flag is not optional on an Apple Silicon Mac.** Cloud Run only runs `linux/amd64` images. A Mac's native Docker build defaults to `arm64` (matching the Mac's own chip) unless explicitly told otherwise. Skipping this flag produces an image that Cloud Run rejects at deploy time with a confusing "must support amd64/linux" manifest error — the build itself succeeds, so this mistake isn't obvious until the deploy step fails.
- `-t asia-south1-docker.pkg.dev/scalancer-pos-prod/scalancer-repo/pos-backend:test` — names ("tags") the resulting image with its full destination path in Artifact Registry, so it's ready to push in the next step. The `:test` at the end is the tag — you could use `:v2`, `:latest`, or anything else, as long as the redeploy command in Step 6 references the same tag.
- The trailing `.` — tells Docker to use the current directory as the *build context*, i.e., what files it's allowed to look at while building. This is why `.dockerignore` matters: anything listed there (secrets, the local virtual environment, `.git`) never enters this process at all.

This step typically takes anywhere from under a minute to a few minutes, depending on whether `requirements.txt` changed (a slower, full dependency reinstall) or just application code changed (fast, since Docker reuses cached layers for anything that didn't change).

---

## Step 4 — Push the image to Artifact Registry

```bash
docker push asia-south1-docker.pkg.dev/scalancer-pos-prod/scalancer-repo/pos-backend:test
```

**What this does:** uploads the freshly built image to Artifact Registry — Google's private storage for Docker images, specific to this project. Cloud Run doesn't read directly from your laptop; it always pulls images from a registry, so this step is what actually makes the new version available to be deployed.

**Note on the tag:** since this reuses the same `:test` tag as before, this push *replaces* what `:test` points to — it doesn't create a second, separate image. Cloud Run's next deploy (Step 6) will pull whatever `:test` currently points to, which is now this new build.

---

## Step 5 — If the database changed, apply the migration to the cloud database

Skip this step entirely if Step 2 was skipped (no database changes in this update).

**5a. Start the Cloud SQL Auth Proxy**, in its own terminal tab — this creates a secure tunnel from your laptop to the real cloud database:
```bash
./cloud-sql-proxy --port 5433 scalancer-pos-prod:asia-south1:scalancer-pos-db
```
Leave this running for the rest of this step. (Port `5433`, not the default `5432` — avoids colliding with a local Postgres server that might already be using `5432` for local development.)

**5b. In a separate terminal tab, apply the migration:**
```bash
cd ~/Desktop/expos/pos-backend
export $(cat app/.env.gcptest | xargs)
alembic upgrade head
```
This points at the cloud database (through the tunnel from 5a) and applies whichever migrations haven't been run yet — Alembic tracks what's already applied, so this is safe to run even if some earlier migrations were already in place.

**5c. Run the schema drift checker as a sanity check:**
```bash
python3 scripts/check_schema_drift.py
```
This compares every database model in the code against what's actually in the connected database, and reports any mismatch. It should print `No missing tables or columns found — models and database schema agree.` If it reports anything else, stop here and investigate before continuing — deploying new code against a database that doesn't actually match what the code expects is exactly the kind of problem this script exists to catch early.

**Why the order matters (migrate before deploy, not after):** the new code (about to be deployed in Step 6) may expect the new column/table to already exist. If the new code goes live *before* the migration runs, any request touching that new field would fail immediately. Running the migration first means the database is already correct and waiting by the time the new code starts receiving traffic.

---

## Step 6 — Redeploy Cloud Run with the new image

```bash
gcloud run deploy scalancer-pos-test \
  --image=asia-south1-docker.pkg.dev/scalancer-pos-prod/scalancer-repo/pos-backend:test \
  --region=asia-south1 \
  --platform=managed \
  --add-cloudsql-instances=scalancer-pos-prod:asia-south1:scalancer-pos-db \
  --min-instances=0 \
  --max-instances=2 \
  --cpu=1 \
  --memory=512Mi \
  --allow-unauthenticated \
  --set-env-vars=RAZORPAY_MODE=test,FIREBASE_KEY_PATH=/secrets/firebase-key.json \
  --set-secrets=DATABASE_URL=DATABASE_URL:latest,JWT_SECRET_KEY=JWT_SECRET_KEY:latest,ADMIN_API_TOKEN=ADMIN_API_TOKEN:latest,RAZORPAY_TEST_KEY_ID=RAZORPAY_TEST_KEY_ID:latest,RAZORPAY_TEST_KEY_SECRET=RAZORPAY_TEST_KEY_SECRET:latest,RAZORPAY_TEST_WEBHOOK_SECRET=RAZORPAY_TEST_WEBHOOK_SECRET:latest,EMAIL_ADDRESS=EMAIL_ADDRESS:latest,EMAIL_PASSWORD=EMAIL_PASSWORD:latest,/secrets/firebase-key.json=FIREBASE_KEY:latest
```

**What happens when this runs:** Cloud Run pulls the image that `:test` currently points to (the one just pushed in Step 4), starts a brand-new container from it, waits until that new container reports itself healthy, and only then switches live traffic over to it — the old version keeps serving requests right up until the new one is confirmed working. This is why redeploying doesn't cause downtime for a healthy new version, and also why a broken new version fails safely: Cloud Run won't route real traffic to a container that never becomes healthy in the first place, so a bad deploy shows up as a failed `gcloud run deploy` command, not as your live app suddenly breaking.

**Note:** this command doesn't need to change between deploys unless the actual configuration changes (a new secret, a different resource limit). It's always the same command reusing `:latest` for every secret, meaning Cloud Run automatically picks up whatever is currently the newest version of each secret without you needing to specify anything new.

---

## Step 7 — Verify it worked

```bash
curl https://scalancer-pos-test-70344915678.asia-south1.run.app/health
```
Expected response: `{"status":"ok","database":"connected"}`.

If the custom domain is active by the time you're reading this:
```bash
curl https://expos.scalancer.com/health
```
Should return the exact same response — if it does, both the raw Cloud Run URL and the custom domain are correctly serving the new deployment.

---

## Step 8 — Check the logs for errors

Especially worth doing right after any deploy that changed real code (not just config):
```bash
gcloud run services logs read scalancer-pos-test --region=asia-south1 --project=scalancer-pos-prod --limit=50
```

Look for:
- Any Python traceback near the top of the output — usually means something crashed on startup (a missing import, a bad env var reference).
- `GET 200` / `POST 200` entries for the endpoints your change actually touches — this confirms real requests are succeeding, not just that the container booted.
- Anything with `ERROR` or a non-2xx status code tied to the feature you just changed.

If something looks wrong here, the traceback almost always points directly at the file and line causing the problem — that's usually enough to know exactly what to fix without further guessing.

---

## Quick troubleshooting reference

| Symptom | Likely cause | Fix |
|---|---|---|
| `docker build` fails with "cannot connect to the Docker daemon" | Docker Desktop isn't running | Open Docker Desktop, wait for the whale icon to go steady, retry |
| `gcloud run deploy` fails with "must support amd64/linux" | Image was built without `--platform linux/amd64` | Rebuild with the flag included (Step 3) |
| `/health` returns `Service Unavailable` after a deploy | Container crashed on startup — check logs (Step 8) for the traceback | Fix whatever the traceback points at, then repeat from Step 3 |
| A request fails with a database column/table error | A migration wasn't applied before deploying the new code | Run Step 5 (migration), then redeploy |
| `curl` to the raw `.run.app` URL works but the custom domain doesn't | Unrelated to this redeploy — a domain/SSL issue, not a code issue | See `GCP_SETUP_COMPLETE_GUIDE.md` Part 6 |

---

## One-sentence summary

Test locally, rebuild and push the Docker image, apply any new database migration to the cloud database before the new code goes live, redeploy Cloud Run with the new image, then verify with a health check and a look at the logs — the same eight steps every time, in the same order, regardless of how big or small the change was.
