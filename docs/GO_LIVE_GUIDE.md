# Go-Live Guide — Moving from Test to Real Deployment

This covers exactly what changes when moving from the test setup (documented in `GCP_SETUP_COMPLETE_GUIDE.md`) to serving real shops with real money. It assumes the test deployment is already working end-to-end — this document only covers the *differences*, not a full re-explanation of things that stay the same.

**The core decision this whole document is built around:** rather than building a second, separate production stack from scratch, the existing test deployment (`scalancer-pos-test` on Cloud Run, `scalancer-pos-db` on Cloud SQL, already wired to `expos.scalancer.com`) gets **upgraded in place** — resized, switched to live payment mode, and hardened — instead of duplicated. This is simpler and avoids redoing the domain/Load Balancer setup, at the cost of not having a separate staging environment afterward unless one is deliberately built later. If a fully separate staging + production split is wanted eventually, that's a bigger, optional follow-up — not required to go live.

---

## 0. First decision: what happens to the test data already in the database?

The database currently has real test bills, test products, test customers — created while testing. Before real shops start using this:

- **Option A — wipe it clean.** If everything in there was just test data, delete it so real shop #1 starts from a genuinely empty state. This needs a deliberate script or manual `DELETE`/`TRUNCATE` pass — not something to do carelessly given foreign key relationships between tables.
- **Option B — keep it.** If any of the test data represents a real shop already using the app (e.g., your own shop for real), leave it as-is.

**Decide this first** — it's much easier to clean up before real shops are also in the same tables than after.

---

## 1. Cloud SQL — resize to the real spec

The test instance is intentionally small and cheap. Before real usage:

```bash
gcloud sql instances patch scalancer-pos-db \
  --project=scalancer-pos-prod \
  --tier=db-custom-1-3840
```

This changes the machine type to 1 vCPU / 3.75GB — the spec sized earlier for a ~100-shop starting point. (Check current shop-count expectations before running this — if launching much larger than ~100 shops immediately, size up further; see the earlier GCP sizing discussion for the 500-5,000+ shop numbers.)

**Note:** this causes a brief restart of the database (usually under a minute) while the resize applies — avoid doing this during a window real shops might be actively using the app, once there are any.

### 1a. Turn on backups and point-in-time recovery — not optional anymore

This was deliberately skipped for the test instance. It is not optional once real shop data exists:

```bash
gcloud sql instances patch scalancer-pos-db \
  --project=scalancer-pos-prod \
  --backup-start-time=02:00 \
  --enable-point-in-time-recovery
```
(`02:00` is UTC — roughly 7:30 AM IST, a low-traffic window.)

### 1b. Consider enabling regional HA (optional, doubles Cloud SQL cost)

The test instance runs zonal (single-zone, no automatic failover). Regional HA adds an automatic standby that takes over if the primary has a problem, at roughly double the Cloud SQL compute cost. Worth it once real revenue depends on uptime; not mandatory for a first launch with a small number of shops. To enable:

```bash
gcloud sql instances patch scalancer-pos-db \
  --project=scalancer-pos-prod \
  --availability-type=REGIONAL
```

---

## 2. Cloud Run — resize and adjust scaling behavior

Update the deploy command's resource flags to the real spec:

```bash
gcloud run deploy scalancer-pos-test \
  --image=asia-south1-docker.pkg.dev/scalancer-pos-prod/scalancer-repo/pos-backend:test \
  --region=asia-south1 \
  --platform=managed \
  --add-cloudsql-instances=scalancer-pos-prod:asia-south1:scalancer-pos-db \
  --min-instances=1 \
  --max-instances=3 \
  --cpu=1 \
  --memory=1Gi \
  --allow-unauthenticated \
  --set-env-vars=RAZORPAY_MODE=live,FIREBASE_KEY_PATH=/secrets/firebase-key.json \
  --set-secrets=... \
  --project=scalancer-pos-prod
```

What changed from the test config, and why:
- **`--min-instances=1`** (was `0`) — a real shop owner ringing up a sale should never hit a cold-start delay. Keeping one instance always warm costs a small amount continuously, but a POS app freezing for a few seconds mid-sale is a much worse outcome than that cost.
- **`--max-instances=3`** (was `2`) — a bit more headroom for real concurrent usage across multiple shops at once.
- **`--memory=1Gi`** (was `512Mi`) — more comfortable margin for report generation (PDF/matplotlib) under real usage, not just light test traffic.
- **`--cpu=1`** — unchanged, still sufficient at this scale.

**The connection-count guardrail from earlier still applies:** `max-instances × 15 (pool_size + max_overflow) ≤ Cloud SQL's max_connections`. At `max-instances=3`, that's 45 connections worst case — comfortably under the `db-custom-1-3840` tier's connection limit, no changes needed there.

**Consider renaming the service** (e.g. from `scalancer-pos-test` to something without "test" in the name) for clarity going forward — this requires deploying as a new service name and then updating the Load Balancer's Serverless NEG (see `GCP_SETUP_COMPLETE_GUIDE.md` §6.2) to point at the new name instead. Optional — the name itself has no functional effect, purely cosmetic/organizational.

---

## 3. Razorpay — switch from test to live

This is the step that makes real payments possible. The app's code already supports this switch cleanly (see `app/services/razorpay_service.py`) — it's purely a matter of credentials and one environment variable.

### 3a. Get live Razorpay credentials

In the Razorpay dashboard, toggle to **Live Mode** (top-right switch), go to **Settings → API Keys**, generate a live key pair (starts with `rzp_live_`).

### 3b. Register the live webhook

Still in live mode: **Settings → Webhooks** → add the same webhook URL already used for test mode (`https://expos.scalancer.com/razorpay-webhook`) — copy the **webhook secret** it generates; this is different from the test-mode webhook secret.

### 3c. Create the three live secrets in Secret Manager

```bash
echo -n "rzp_live_..." | gcloud secrets create RAZORPAY_LIVE_KEY_ID --data-file=- --project=scalancer-pos-prod
echo -n "YOUR_LIVE_KEY_SECRET" | gcloud secrets create RAZORPAY_LIVE_KEY_SECRET --data-file=- --project=scalancer-pos-prod
echo -n "YOUR_LIVE_WEBHOOK_SECRET" | gcloud secrets create RAZORPAY_LIVE_WEBHOOK_SECRET --data-file=- --project=scalancer-pos-prod

for SECRET in RAZORPAY_LIVE_KEY_ID RAZORPAY_LIVE_KEY_SECRET RAZORPAY_LIVE_WEBHOOK_SECRET; do
  gcloud secrets add-iam-policy-binding $SECRET \
    --member="serviceAccount:70344915678-compute@developer.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor" \
    --project=scalancer-pos-prod
done
```

### 3d. Flip the mode and add the new secrets to the deploy

In the `gcloud run deploy` command (Section 2 above): change `RAZORPAY_MODE=test` to `RAZORPAY_MODE=live`, and add the three new secrets to `--set-secrets`:
```
RAZORPAY_LIVE_KEY_ID=RAZORPAY_LIVE_KEY_ID:latest,RAZORPAY_LIVE_KEY_SECRET=RAZORPAY_LIVE_KEY_SECRET:latest,RAZORPAY_LIVE_WEBHOOK_SECRET=RAZORPAY_LIVE_WEBHOOK_SECRET:latest
```
(The `RAZORPAY_TEST_*` secrets can stay in the deploy command too, or be removed — the code only reads whichever set matches the active `RAZORPAY_MODE`, so leaving both wired up is harmless and makes switching back to test mode later trivial if ever needed for debugging.)

### 3e. Verify the mode after deploying

```bash
curl -H "X-Admin-Token: YOUR_ADMIN_API_TOKEN" https://expos.scalancer.com/admin/razorpay-mode
```
Should return `{"mode": "live", "key_id": "rzp_live_..."}`. If the key/mode mismatch safety check in `razorpay_service.py` catches a problem (e.g. a test key accidentally left in a live slot), the container will refuse to start and the deploy will fail loudly instead of silently taking real payments incorrectly — check the logs if that happens.

### 3f. Test with a real ₹1 transaction

Since live mode can't be tested with fake card numbers the way test mode can, do one small real transaction through the actual app, confirm it shows up correctly in the Razorpay dashboard and activates the subscription as expected, then refund it to yourself from the dashboard.

---

## 4. Double-check the things that don't need to change, but are worth confirming

- **Domain and SSL** — already live at `expos.scalancer.com`, nothing to redo here. The Android app doesn't need any URL change either, since it already points at this same domain.
- **CORS** — still not relevant unless a browser-based tool exists; leave as configured.
- **Cloud SQL public IP exposure** — already confirmed safe (no open authorized networks) during the test phase; nothing changes here.
- **Budget alert** — revisit the ceiling amount now that real costs will be higher than the test setup (Cloud SQL resize, `min-instances=1`, potentially HA) — the old test-scale budget alert threshold may now be too low and could fire immediately on the new baseline cost. Update it in **Billing → Budgets & Alerts** to a number that reflects the new expected monthly cost with headroom.
- **Schema drift check** — run `python3 scripts/check_schema_drift.py` one more time against the database before opening it to real shops, as a final sanity check that everything the code expects actually exists.

---

## 5. Final go-live checklist

- [ ] Decided what happens to existing test data (wiped or kept deliberately)
- [ ] Cloud SQL resized to real spec
- [ ] Cloud SQL backups + point-in-time recovery turned on
- [ ] Considered/decided on regional HA
- [ ] Cloud Run resized (`min-instances=1`, adjusted memory/max-instances)
- [ ] Live Razorpay keys generated and live webhook registered
- [ ] Live secrets created in Secret Manager and granted to Cloud Run's service account
- [ ] `RAZORPAY_MODE=live` set and deployed
- [ ] `/admin/razorpay-mode` confirms `"mode": "live"`
- [ ] One real ₹1 transaction tested and refunded
- [ ] Budget alert threshold updated for real-world costs
- [ ] Schema drift check run one final time, clean
- [ ] `curl https://expos.scalancer.com/health` confirms everything still healthy after all the above changes

Once every box is checked, the deployment is genuinely serving real shops with real payments — not a test setup wearing a real domain.
