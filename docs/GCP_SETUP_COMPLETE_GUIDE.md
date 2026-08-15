# Complete GCP Hosting Setup — Full Flow, Start to End

This is the full, in-order story of how the `pos-backend` app got connected to and deployed on Google Cloud, with every command used. Written so it can be followed step by step, either to redo this setup from scratch or to understand what each piece is doing and why. Companion to `DOCKER_GUIDE.md` and `DATABASE_MIGRATIONS_GUIDE.md` — this document focuses on the sequence and the "why," those focus on deeper technical detail on specific pieces.

---

## Part 1 — Setting up identity and access

This part only ever needs to be done once per Google account / project. Everything after Part 1 is what gets repeated for future deployments — see the **"Next time" quick reference** at the very end of this document for the condensed version once this is all familiar.

### 1.1 Create a dedicated Google account

Rather than reusing a personal Gmail account, a fresh Google account was created specifically to own everything on Google Cloud, so billing, permissions, and infrastructure stay completely separate from any personal account.

1. Go to [accounts.google.com/signup](https://accounts.google.com/signup).
2. Fill in a name, then on the username screen pick a Gmail address (e.g. `scalancer25@gmail.com`).
3. Set a password, verify a phone number if asked, accept the terms.
4. This is now the account used for every step below — stay logged into it in the browser for the console steps, and it's what `gcloud auth login` (1.6) points the terminal at too.

*(Why not just use `admin@scalancer.com`? That address already receives real mail through Hostinger, and Google's "use my current email as a Google login" option wasn't available in this signup flow at the time — so a plain new Gmail-based account was used instead, kept logically separate as the "infrastructure" identity.)*

### 1.2 Create the GCP project

A **project** in Google Cloud is the container that holds every resource for one piece of work — the server, the database, the secrets, the billing, all of it. Nothing exists outside of a project.

1. Go to [console.cloud.google.com](https://console.cloud.google.com), logged in as the account from 1.1.
2. First time here, accept the Terms of Service if prompted.
3. Click the **project dropdown** at the very top of the page (next to the "Google Cloud" logo — it'll say "Select a project" the first time).
4. Click **"New Project."**
5. **Project name:** `scalancer-pos-prod` (or whatever name — this becomes the human-readable label).
6. **Organization:** leave as "No organization" unless Google Workspace is set up for the domain (a separate, optional step — see the Workspace discussion earlier in this project's history if that's wanted later).
7. Click **Create.** Takes a few seconds; a notification bell in the top bar shows progress.
8. Once created, make sure the new project is actually **selected** in that same dropdown before doing anything else — GCP silently keeps using whatever project was previously selected otherwise, which is a common source of "why can't gcloud find my resource" confusion.

### 1.3 Link billing

Nothing in GCP runs — not even small test resources — without a billing account attached to the project.

1. In the left sidebar (☰ menu), go to **Billing**.
2. If this is the very first project ever created on this account, it'll prompt to create a new billing account — click **"Link a billing account"** or **"Create billing account."**
3. Fill in payment details (card).
4. Confirm the correct project (`scalancer-pos-prod`) is linked to this billing account — the Billing overview page shows which projects are attached.
5. Check whether a free trial credit is currently being offered at this step — Google periodically changes this, so treat whatever's shown on screen as the current truth rather than assuming a fixed amount.

### 1.4 Set a budget alert

This is what makes an unexpected cost spike show up as an email instead of a surprise bill later — cheap insurance, takes under a minute.

1. Still in **Billing**, click **"Budgets & Alerts"** in the left sidebar.
2. Click **"Create Budget."**
3. **Scope:** select the project `scalancer-pos-prod` specifically (not "all projects," in case more get added later).
4. **Amount:** set a ceiling well above expected cost but low enough to actually catch a real problem — e.g. ₹4,000 or $50 for a test-scale setup.
5. **Actions:** leave the default alert thresholds (50%, 90%, 100% of budget) — each one triggers an email to the billing account's contact address.
6. Click **Finish.**

### 1.5 Install the `gcloud` command-line tool

`gcloud` is the tool that lets a terminal talk to Google Cloud directly, instead of clicking through the console website for every action — everything from Part 2 onward uses it.

```bash
brew install google-cloud-sdk
```

Confirm it installed correctly:
```bash
gcloud --version
```

### 1.6 Log `gcloud` into the right account

```bash
gcloud auth login scalancer25@gmail.com
```

This opens a browser window to sign in (or confirm the already-logged-in session) as that account, then remembers that login for every future `gcloud` command run from this machine — no need to repeat this unless switching accounts or the login expires.

To check which account(s) `gcloud` currently knows about and which one is active:
```bash
gcloud auth list
```
The account with a `*` next to it is the one every command will use.

### 1.7 Set the active project

```bash
gcloud config set project scalancer-pos-prod
```

Every command after this defaults to acting on `scalancer-pos-prod` unless told otherwise.

### 1.8 Set Application Default Credentials

A second, separate credential store — used by tools like the Cloud SQL Auth Proxy (below) rather than `gcloud` itself:

```bash
gcloud auth application-default login
```

---

## Part 2 — Creating the database

### 2.1 Create the Cloud SQL (PostgreSQL) instance

Done via Console → SQL → Create Instance → PostgreSQL:

- Instance ID: `scalancer-pos-db`
- Region: `asia-south1` (Mumbai — closest to real users, and required for GST/India-specific compliance reasoning)
- Machine type: a small/shared-core tier for testing (kept cheap on purpose — this is not the size used once real shops are on it)
- Zonal availability: **Single zone** (no automatic failover — acceptable for a test instance, revisit before real customer data)
- Storage: 10–20GB SSD

### 2.2 Create the actual database inside the instance

A Cloud SQL *instance* is the server; a *database* still needs to be created on it:

Console → the instance → **Databases** tab → **Create Database** → named `ExPOS`.

### 2.3 Install and run the Cloud SQL Auth Proxy

A laptop cannot reach a Cloud SQL database directly over the open internet — this is intentional, for security. The **Cloud SQL Auth Proxy** creates a secure, authenticated tunnel between the laptop and the database, using the Google login from step 1.6/1.8 to prove identity instead of relying on IP-based access rules.

```bash
curl -o cloud-sql-proxy https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.14.0/cloud-sql-proxy.darwin.arm64
chmod +x cloud-sql-proxy
./cloud-sql-proxy --port 5433 scalancer-pos-prod:asia-south1:scalancer-pos-db
```

(Port `5433` instead of the default `5432` — avoids colliding with a local Postgres server that may already be listening on 5432 for local development.)

Leave this running in its own terminal tab — it opens `127.0.0.1:5433` on the laptop and quietly forwards everything through to the real Cloud SQL instance.

### 2.4 Point a throwaway `.env` at the tunnel

```bash
# app/.env.gcptest
DATABASE_URL=postgresql://postgres:YOUR_REAL_PASSWORD@127.0.0.1:5433/ExPOS
```

### 2.5 Run every database migration against the fresh database

```bash
cd ~/Desktop/expos/pos-backend
export $(cat app/.env.gcptest | xargs)
alembic upgrade head
```

This builds all ~48 tables from scratch, using the same migration files that define the app's database structure in version control — nothing manually clicked together, fully reproducible.

### 2.6 Verify

```bash
psql "$DATABASE_URL" -c "\dt"
```

---

## Part 3 — Packaging the app

### 3.1 Confirm Docker Desktop is running

The `docker` CLI needs the Docker Desktop application open in the background to actually build anything — check for the whale icon in the Mac menu bar.

### 3.2 Enable Artifact Registry and create a repository

Artifact Registry is Google's private storage for Docker images — think of it as a private app store just for this project's own containers.

```bash
gcloud services enable artifactregistry.googleapis.com --project=scalancer-pos-prod

gcloud artifacts repositories create scalancer-repo \
  --repository-format=docker \
  --location=asia-south1 \
  --project=scalancer-pos-prod
```

### 3.3 Let Docker authenticate to Artifact Registry

```bash
gcloud auth configure-docker asia-south1-docker.pkg.dev
```

### 3.4 Build the image

```bash
cd ~/Desktop/expos/pos-backend
docker build --platform linux/amd64 \
  -t asia-south1-docker.pkg.dev/scalancer-pos-prod/scalancer-repo/pos-backend:test .
```

`--platform linux/amd64` matters specifically on Apple Silicon Macs: Cloud Run only runs `linux/amd64` images, but a Mac's native Docker build defaults to `arm64` (matching the Mac's own chip) unless told otherwise — building without this flag produces an image Cloud Run will flatly reject at deploy time.

### 3.5 Push the image

```bash
docker push asia-south1-docker.pkg.dev/scalancer-pos-prod/scalancer-repo/pos-backend:test
```

---

## Part 4 — Storing secrets

Rather than putting real passwords and API keys directly into deploy commands (where they'd sit in shell history and Cloud Run's console in plain text), everything sensitive goes into **Secret Manager** — a secure vault — and only the specific service that needs it is granted permission to read it.

### 4.1 Enable the API

```bash
gcloud services enable secretmanager.googleapis.com --project=scalancer-pos-prod
```

### 4.2 Create one secret per sensitive value

```bash
echo -n "postgresql://postgres:YOUR_PASSWORD@/ExPOS?host=/cloudsql/scalancer-pos-prod:asia-south1:scalancer-pos-db" | \
  gcloud secrets create DATABASE_URL --data-file=- --project=scalancer-pos-prod

echo -n "YOUR_JWT_SECRET" | \
  gcloud secrets create JWT_SECRET_KEY --data-file=- --project=scalancer-pos-prod

echo -n "YOUR_ADMIN_TOKEN" | \
  gcloud secrets create ADMIN_API_TOKEN --data-file=- --project=scalancer-pos-prod

echo -n "rzp_test_..." | \
  gcloud secrets create RAZORPAY_TEST_KEY_ID --data-file=- --project=scalancer-pos-prod

echo -n "YOUR_RAZORPAY_TEST_SECRET" | \
  gcloud secrets create RAZORPAY_TEST_KEY_SECRET --data-file=- --project=scalancer-pos-prod

echo -n "YOUR_WEBHOOK_SECRET" | \
  gcloud secrets create RAZORPAY_TEST_WEBHOOK_SECRET --data-file=- --project=scalancer-pos-prod

echo -n "your-email@gmail.com" | \
  gcloud secrets create EMAIL_ADDRESS --data-file=- --project=scalancer-pos-prod

echo -n "YOUR_APP_PASSWORD" | \
  gcloud secrets create EMAIL_PASSWORD --data-file=- --project=scalancer-pos-prod
```

One secret is a whole **file**, not a single value — the Firebase service-account credentials used for push notifications:

```bash
gcloud secrets create FIREBASE_KEY --data-file=app/firebase-key.json --project=scalancer-pos-prod
```

`echo -n` (not plain `echo`) matters — it avoids adding an invisible trailing newline character into the secret, which can quietly break exact-string comparisons later.

### 4.3 Find Cloud Run's service account

Cloud Run runs containers as a specific Google-managed identity — this identity needs explicit permission to read each secret:

```bash
gcloud iam service-accounts list --project=scalancer-pos-prod
```

Looks like: `70344915678-compute@developer.gserviceaccount.com`

### 4.4 Grant that service account access to every secret

```bash
for SECRET in DATABASE_URL JWT_SECRET_KEY ADMIN_API_TOKEN RAZORPAY_TEST_KEY_ID RAZORPAY_TEST_KEY_SECRET RAZORPAY_TEST_WEBHOOK_SECRET EMAIL_ADDRESS EMAIL_PASSWORD FIREBASE_KEY; do
  gcloud secrets add-iam-policy-binding $SECRET \
    --member="serviceAccount:70344915678-compute@developer.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor" \
    --project=scalancer-pos-prod
done
```

---

## Part 5 — Deploying to Cloud Run

Cloud Run is the actual service that runs the container and gives it a public web address.

### 5.1 The deploy command

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

What each piece means:
- `--add-cloudsql-instances` — wires Cloud Run's own built-in Cloud SQL connector, a production equivalent of the Auth Proxy used locally in Part 2.
- `--min-instances=0` / `--max-instances=2` — how many copies of the app can run at once; `0` minimum means it can shut down completely when idle (fine for testing, not for real traffic where a cold start would show as a delay to a real user).
- `--allow-unauthenticated` — makes the URL publicly reachable, needed since the Android app calls it directly. Security comes from the app's own login/token system, not network-level blocking.
- `--set-env-vars` — plain, non-sensitive configuration values.
- `--set-secrets` — the bridge between Secret Manager (Part 4) and the running container. Two different formats appear here: `ENV_VAR_NAME=SECRET:latest` injects a secret as an environment variable; `/file/path=SECRET:latest` (note the leading `/`) mounts it as an actual file instead.

### 5.2 Verify it's alive

```bash
curl https://scalancer-pos-test-70344915678.asia-south1.run.app/health
```

Expected: `{"status":"ok","database":"connected"}` — proof the whole chain (Cloud Run → Cloud SQL → Secret Manager → Firebase) is wired together correctly.

### 5.3 Reading logs when something fails

```bash
gcloud run services logs read scalancer-pos-test --region=asia-south1 --project=scalancer-pos-prod --limit=100
```

---

## Part 6 — Giving it a real domain name

Rather than using the long auto-generated `*.run.app` address forever, the domain `expos.scalancer.com` (already owned via Hostinger) was connected to this Cloud Run service.

Cloud Run has a simpler built-in "domain mappings" feature, but it's Preview-only (not fully production-supported) and not reliably available in every region. Instead, an **External HTTPS Load Balancer** was set up — more steps, but the fully-supported, production-grade path.

### 6.1 Reserve a static IP address

```bash
gcloud compute addresses create scalancer-pos-ip --global --project=scalancer-pos-prod
gcloud compute addresses describe scalancer-pos-ip --global --project=scalancer-pos-prod --format="value(address)"
```

### 6.2 Create a Serverless NEG pointing at the Cloud Run service

A NEG (Network Endpoint Group) is how the load balancer finds the actual Cloud Run service to send traffic to:

```bash
gcloud compute network-endpoint-groups create scalancer-pos-neg \
  --region=asia-south1 \
  --network-endpoint-type=serverless \
  --cloud-run-service=scalancer-pos-test \
  --project=scalancer-pos-prod
```

### 6.3 Create a backend service and attach the NEG

```bash
gcloud compute backend-services create scalancer-pos-backend \
  --global --load-balancing-scheme=EXTERNAL_MANAGED --project=scalancer-pos-prod

gcloud compute backend-services add-backend scalancer-pos-backend \
  --global \
  --network-endpoint-group=scalancer-pos-neg \
  --network-endpoint-group-region=asia-south1 \
  --project=scalancer-pos-prod
```

### 6.4 Create a URL map

Routes all incoming traffic to that backend service:

```bash
gcloud compute url-maps create scalancer-pos-urlmap \
  --default-service=scalancer-pos-backend \
  --project=scalancer-pos-prod
```

### 6.5 Create a Google-managed SSL certificate

```bash
gcloud compute ssl-certificates create scalancer-pos-cert \
  --domains=expos.scalancer.com \
  --global --project=scalancer-pos-prod
```

Stays in `PROVISIONING` status until DNS (step 6.8) correctly points at the IP AND Google's system detects and validates it — this can take anywhere from 15 minutes to a couple of hours.

### 6.6 Create the HTTPS target proxy

```bash
gcloud compute target-https-proxies create scalancer-pos-https-proxy \
  --ssl-certificates=scalancer-pos-cert \
  --url-map=scalancer-pos-urlmap \
  --project=scalancer-pos-prod
```

### 6.7 Create the forwarding rule

Binds the static IP (6.1) to the HTTPS proxy (6.6) on port 443 — this is the piece that actually makes the IP address "live":

```bash
gcloud compute forwarding-rules create scalancer-pos-https-rule \
  --address=scalancer-pos-ip \
  --global \
  --target-https-proxy=scalancer-pos-https-proxy \
  --ports=443 \
  --project=scalancer-pos-prod
```

### 6.8 Add the DNS record in Hostinger

In Hostinger's DNS Zone Editor, added:
- Type: `A`
- Name/Host: `expos`
- Points to: the static IP from step 6.1
- TTL: default

### 6.9 Wait, then verify

```bash
dig expos.scalancer.com +short   # should match the static IP
gcloud compute ssl-certificates describe scalancer-pos-cert --global --project=scalancer-pos-prod --format="value(managed.status)"
# once this shows ACTIVE:
curl https://expos.scalancer.com/health
```

---

## Part 7 — Locking down the loose ends

- **CORS** — a browser-security setting, irrelevant to the Android app itself (it doesn't send the browser-style `Origin` header CORS checks against), but pre-configured for whenever a browser-based tool exists:
  ```bash
  gcloud run services update scalancer-pos-test \
    --region=asia-south1 --project=scalancer-pos-prod \
    --update-env-vars=CORS_ALLOWED_ORIGINS=https://expos.scalancer.com
  ```
- **Database exposure check** — confirmed Cloud SQL's public IP has no open "authorized networks" entries, meaning nothing can reach it except through the authenticated proxy/connector used throughout this whole setup:
  ```bash
  gcloud sql instances describe scalancer-pos-db --project=scalancer-pos-prod --format="yaml(settings.ipConfiguration)"
  ```
- **Budget alert** — set in Part 1.4, already active for the whole project.

---

## The full picture in one sentence

A dedicated Google account and project were created, billing and a cost alert were attached, a Cloud SQL database was built and populated via a secure local tunnel, the app was packaged into a Docker image and pushed to a private registry, every sensitive value was stored in Secret Manager and granted only to the specific service that needs it, Cloud Run pulled all of that together into a live, publicly reachable backend, and a Load Balancer plus a Google-managed SSL certificate connected that backend to the real domain `expos.scalancer.com` — with every step reproducible from the commands in this document.

---

## Next time — quick reference

Part 1 (account, project, billing, `gcloud` install/login) is **one-time setup** — skip it entirely once it's already done. Everything below is what actually repeats for a fresh deploy, assuming the project, database instance, secrets, and domain/load-balancer already exist from a first pass through this guide. Realistically a 5-10 minute process once each command is familiar — the slow parts (SSL cert provisioning, DNS propagation) only happen once, during initial domain setup, not on every deploy.

**If only the code changed (most common case) — rebuild, repush, redeploy:**
```bash
cd ~/Desktop/expos/pos-backend
docker build --platform linux/amd64 -t asia-south1-docker.pkg.dev/scalancer-pos-prod/scalancer-repo/pos-backend:test .
docker push asia-south1-docker.pkg.dev/scalancer-pos-prod/scalancer-repo/pos-backend:test
gcloud run deploy scalancer-pos-test \
  --image=asia-south1-docker.pkg.dev/scalancer-pos-prod/scalancer-repo/pos-backend:test \
  --region=asia-south1 --platform=managed \
  --add-cloudsql-instances=scalancer-pos-prod:asia-south1:scalancer-pos-db \
  --min-instances=0 --max-instances=2 --cpu=1 --memory=512Mi \
  --allow-unauthenticated \
  --set-env-vars=RAZORPAY_MODE=test,FIREBASE_KEY_PATH=/secrets/firebase-key.json \
  --set-secrets=DATABASE_URL=DATABASE_URL:latest,JWT_SECRET_KEY=JWT_SECRET_KEY:latest,ADMIN_API_TOKEN=ADMIN_API_TOKEN:latest,RAZORPAY_TEST_KEY_ID=RAZORPAY_TEST_KEY_ID:latest,RAZORPAY_TEST_KEY_SECRET=RAZORPAY_TEST_KEY_SECRET:latest,RAZORPAY_TEST_WEBHOOK_SECRET=RAZORPAY_TEST_WEBHOOK_SECRET:latest,EMAIL_ADDRESS=EMAIL_ADDRESS:latest,EMAIL_PASSWORD=EMAIL_PASSWORD:latest,/secrets/firebase-key.json=FIREBASE_KEY:latest
curl https://scalancer-pos-test-70344915678.asia-south1.run.app/health
```
No secret or database changes needed — the existing ones are reused automatically via `:latest`.

**If the database schema changed (new migration added):**
```bash
./cloud-sql-proxy --port 5433 scalancer-pos-prod:asia-south1:scalancer-pos-db   # separate terminal tab, leave running
export $(cat app/.env.gcptest | xargs)
alembic upgrade head
python3 scripts/check_schema_drift.py   # sanity check — should print "No missing tables or columns found"
```
Then do the rebuild/redeploy above as usual.

**If a secret value changed** (rotated password, new API key, etc.):
```bash
echo -n "NEW_VALUE" | gcloud secrets versions add SECRET_NAME --data-file=- --project=scalancer-pos-prod
```
Then redeploy (the deploy command above) so Cloud Run picks up the new version — it doesn't auto-refresh a running container's secrets on its own.

**Sanity checklist before calling a deploy "done":**
1. `curl .../health` returns `{"status":"ok","database":"connected"}`
2. `gcloud run services logs read scalancer-pos-test --region=asia-south1 --project=scalancer-pos-prod --limit=50` shows no tracebacks
3. If the domain is expected to be live: `curl https://expos.scalancer.com/health` matches the raw `.run.app` result
