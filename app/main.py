import os
from app import logging_config  # noqa: F401 — sets up logging.basicConfig before anything else logs
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, SessionLocal
from sqlalchemy import text
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from slowapi.middleware import SlowAPIMiddleware
from app.rate_limit import limiter

from app.models import *

# Registers SQLAlchemy listeners that auto-invalidate the AI caches on relevant writes.
from app.util import ai_cache_hooks  # noqa: F401

from app.routes import auth_routes, profit_routes, sales_routes
from app.routes import product_routes
from app.routes import bill_routes
from app.routes import report_routes
from app.routes import shop_routes
from app.routes import billing_settings_routes
from app.routes.security_routes import router as security_router
from app.routes import admin_routes
from app.routes.admin_catalog_routes import router as admin_catalog_router
from app.routes.analytics_routes import router as analytics_router
from app.routes import subscription_routes as subscription
from app.routes import subscription_payment_routes
from app.routes import gst_routes
from app.routes.global_catalog_routes import router as global_catalog_router
from app.routes.purchase_routes import router as purchase_router
from app.routes.purchase_return_routes import router as purchase_return_router
from app.routes.scrap_routes import router as scrap_router
from app.routes.gst_sales_invoice_routes import router as gst_sales_invoice_router
from app.routes.purchase_batch_routes import router as purchase_batch_router
from app.routes.credit_note_routes import router as credit_note_router
from app.routes.user_event_log_routes import router as user_event_log_router
from app.routes.diagnostic_report_routes import router as diagnostic_report_router



from apscheduler.schedulers.background import BackgroundScheduler
from app.services.expiry_service import check_subscriptions
from app.routes import credit_routes as credit

from app.routes import inventory_routes



app = FastAPI(
    title="POS Backend",
    version="1.0.0"
)

# Rate limiting (slowapi) — protects the auth endpoints (login, OTP
# request/verify, forgot-password) from brute-force/abuse now that this
# is reachable from the public internet instead of just the home
# network. Individual limits are set per-route in auth_routes.py via
# @limiter.limit(...); this just wires the shared Limiter instance
# (app/rate_limit.py) into the app and defines what happens when a
# limit is hit (429, not an unhandled exception).
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS
# CORS_ALLOWED_ORIGINS is a comma-separated list of exact origins, e.g.
# "https://app.example.com,https://admin.example.com". If unset (typical
# for local dev), we fall back to "*" but print a loud warning — this
# app is served to a mobile client, not a browser, so allow_origins="*"
# is low-risk here, but it should still be pinned down before any
# browser-based admin/dashboard surface is added.
logger = logging.getLogger(__name__)

_cors_env = os.getenv("CORS_ALLOWED_ORIGINS", "").strip()
if _cors_env:
    _cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()]
else:
    _cors_origins = ["*"]
    logger.warning(
        "CORS_ALLOWED_ORIGINS is not set — falling back to allow_origins=['*']. "
        "Set CORS_ALLOWED_ORIGINS before hosting this behind a public URL that "
        "browsers can reach."
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────────────────────────────
# Schema changes now live entirely in Alembic (migrations/versions/).
# The 28 ad-hoc startup ALTER functions that used to run here (belt-
# and-braces table/column checks going back to the invoice-date column
# through the onboarding/subscription-tier backfill) have been ported
# 1:1 into migrations 0015 through 0043 — same idempotent logic, now
# versioned and reviewable instead of firing unconditionally on every
# boot. Run `alembic upgrade head` to apply schema changes; this file
# no longer does it implicitly. See migrations/versions/0015_*.py
# onward for the ported logic, one file per original function.
#
# `Base.metadata.create_all(bind=engine)` used to run here as well, in
# addition to Alembic. Removed (2026-08-14): with 46 migrations now the
# sole source of schema truth, create_all() alongside them is a silent
# schema-drift risk — a model change without a matching migration would
# get create_all()'d into existence without ever going through Alembic,
# leaving the migration history lying about what's actually in the DB.
# Alembic (`alembic upgrade head`) is now the only thing that creates or
# alters tables.
# ──────────────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────
# Seed the default plans so GET /subscription/plans has something to
# return on a fresh deploy. Idempotent — only inserts a plan_code that
# doesn't already exist, never overwrites a price an admin may have
# since changed by hand in the DB. This is also how the four new
# billing-cycle tiers (2026-08-02) reach an ALREADY-deployed database:
# their plan_codes have never existed before, so the very next app
# restart inserts them via this same idempotent path — no migration
# needed for that part (a migration IS needed when an existing row's
# price changes instead — see 0013 for the base/premium monthly price
# update).
#
# Pricing (2026-08-02) — quarterly/half-yearly/yearly discounts follow
# the same ~9% / ~17% / ~29% curve on both tiers so the savings feel
# consistent regardless of which tier a shop picks. The two longest
# commitments also get bonus days on top of the discount (15 extra days
# on half-yearly, 30 extra — a 13th month — on yearly), stacked as a
# separate incentive from the price break itself:
#   Base:    699/mo · 1,899/3mo (90d) · 3,499/6mo (195d) · 5,999/12mo (395d)
#   Premium: 999/mo · 2,699/3mo (90d) · 4,999/6mo (195d) · 8,499/12mo (395d)
# ──────────────────────────────────────────────────────────────────────
def _seed_default_plans() -> None:
    from app.models.plan import Plan

    db = SessionLocal()
    try:
        existing = {p.plan_code: p for p in db.query(Plan).all()}
        defaults = [
            Plan(plan_code="base_monthly", name="Base", tier="base", price_paise=69900, duration_days=30, is_active=True),
            Plan(plan_code="base_quarterly", name="Base (3 Months)", tier="base", price_paise=189900, duration_days=90, is_active=True),
            Plan(plan_code="base_half_yearly", name="Base (6 Months)", tier="base", price_paise=349900, duration_days=195, is_active=True),
            Plan(plan_code="base_yearly", name="Base (12 Months)", tier="base", price_paise=599900, duration_days=395, is_active=True),

            Plan(plan_code="premium_monthly", name="Premium (Monthly)", tier="premium", price_paise=99900, duration_days=30, is_active=True),
            Plan(plan_code="premium_quarterly", name="Premium (3 Months)", tier="premium", price_paise=269900, duration_days=90, is_active=True),
            Plan(plan_code="premium_half_yearly", name="Premium (6 Months)", tier="premium", price_paise=499900, duration_days=195, is_active=True),
            Plan(plan_code="premium_yearly", name="Premium (12 Months)", tier="premium", price_paise=849900, duration_days=395, is_active=True),
        ]
        for plan in defaults:
            if plan.plan_code not in existing:
                db.add(plan)
        db.commit()

        # Self-healing correction for the two plan_codes that pre-date the
        # 2026-08-02 repricing (base_monthly used to be free-forever,
        # premium_monthly was ₹299) — migration 0013 covers this too, but
        # requiring a manual `alembic upgrade head` against a database this
        # app can't always reach directly turned out to be a real deploy
        # blocker. Doing the correction here as well means the fix lands on
        # the very next app restart, no separate migration step required.
        # Safe to run every boot: it's a no-op once the values already
        # match, and never touches any plan_code outside this fixed pair.
        legacy_fixes = {
            "base_monthly": {"price_paise": 69900, "duration_days": 30},
            "premium_monthly": {"price_paise": 99900},
        }
        changed = False
        for code, expected in legacy_fixes.items():
            plan = existing.get(code)
            if plan is None:
                continue
            for field, value in expected.items():
                if getattr(plan, field) != value:
                    setattr(plan, field, value)
                    changed = True
        if changed:
            db.commit()
    finally:
        db.close()

try:
    _seed_default_plans()
except Exception as e:  # pragma: no cover
    logger.warning("default plan seeding skipped: %s", e)


# Routers
app.include_router(auth_routes.router)
app.include_router(product_routes.router)
app.include_router(bill_routes.router)
app.include_router(report_routes.router)
app.include_router(shop_routes.router)
app.include_router(billing_settings_routes.router)
app.include_router(security_router)
app.include_router(admin_routes.router)
app.include_router(admin_catalog_router)
app.include_router(analytics_router)
app.include_router(subscription.router)
app.include_router(subscription_payment_routes.router)
app.include_router(credit.router)
app.include_router(inventory_routes.router)
app.include_router(sales_routes.router)
app.include_router(profit_routes.router)
app.include_router(gst_routes.router)
app.include_router(global_catalog_router)
app.include_router(purchase_router)
app.include_router(purchase_return_router)
app.include_router(scrap_router)
app.include_router(gst_sales_invoice_router)
app.include_router(purchase_batch_router)
app.include_router(credit_note_router)
app.include_router(user_event_log_router)
app.include_router(diagnostic_report_router)
from app.routes.purchase_import_details_routes import router as purchase_import_details_router
app.include_router(purchase_import_details_router)
from app.routes.import_service_routes import router as import_service_router
app.include_router(import_service_router)
from app.routes.category_routes import router as category_router
app.include_router(category_router)
from app.routes.customer_routes import router as customer_router
app.include_router(customer_router)
# Supplier master — GET /suppliers, /suppliers/by-gstin, /suppliers/by-name,
# POST /suppliers/sync, /suppliers/account.
from app.routes.supplier_routes import router as supplier_router
app.include_router(supplier_router)
# Units
from app.schemas.product_schema import UnitListResponse

@app.get("/units", response_model=UnitListResponse)
def get_units():
    return {"units": ["piece", "kg", "litre", "gram", "ml", "box"]}


# Root
@app.get("/")
def root():
    return {"message": "POS Backend Running Successfully!"}


# Health check — Cloud Run (and any other platform-level uptime probe)
# hits this to decide whether to route traffic to an instance. Verifies
# the DB connection actually works, not just that the process is alive:
# a container can boot fine and still be unable to reach Cloud SQL (bad
# credentials, VPC connector misconfigured, DB paused), and a bare 200
# with no DB check would mask exactly that failure mode.
@app.get("/health")
def health_check():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        # Non-2xx so the platform's health probe actually treats this as
        # unhealthy — a 200 with an "error" body in it would be silently
        # ignored by most infra-level checks, which only look at the
        # status code.
        raise HTTPException(status_code=503, detail=f"database unreachable: {e}")
    finally:
        db.close()


# ──────────────────────────────────────────────────────────────────────
# Scheduler single-owner lock (2026-08-14).
#
# gunicorn runs this app with multiple worker processes (see Dockerfile,
# --workers 2). Each worker imports this module independently, so
# without a guard, every worker would create its own BackgroundScheduler
# and register the same 4 jobs — including order reconciliation, which
# checks Razorpay orders every 15 minutes and can activate a subscription
# / redeem a coupon when it finds one paid. That path was found to be
# vulnerable to a genuine double-activation race under true concurrent
# execution (read-then-write status check, no DB-level lock — see
# order_reconciliation_service.py for the row-level fix on the query
# side). Running two schedulers concurrently is the other half of that
# risk, so only one process should ever run the scheduler at all.
#
# Fix: a Postgres session-level advisory lock. Every worker tries to
# acquire it at import time; only the one that succeeds starts the
# scheduler. The connection used to acquire the lock is kept open for
# the life of that process — a session-level advisory lock releases
# automatically when its connection closes, so if the lock-holding
# worker dies/restarts, another worker (or, if this is later scaled
# horizontally across multiple instances, another instance) can pick it
# up. No coordination beyond Postgres itself is required, and this
# keeps working correctly regardless of how many workers or instances
# end up running in the future.
# ──────────────────────────────────────────────────────────────────────
_SCHEDULER_ADVISORY_LOCK_ID = 928374651  # arbitrary constant, unique to this job
_scheduler_lock_conn = None


def _acquire_scheduler_lock() -> bool:
    global _scheduler_lock_conn
    try:
        conn = engine.connect()
        acquired = conn.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": _SCHEDULER_ADVISORY_LOCK_ID},
        ).scalar()
        if acquired:
            _scheduler_lock_conn = conn  # kept open deliberately — do not close
            return True
        conn.close()
        return False
    except Exception as e:  # pragma: no cover
        logger.warning(
            "Scheduler advisory lock could not be acquired (%s) — scheduler will "
            "not start on this worker.",
            e,
        )
        return False


def run_expiry_check():
    db = SessionLocal()
    check_subscriptions(db)
    db.close()


def run_order_reconciliation():
    from app.services.order_reconciliation_service import reconcile_stuck_orders
    db = SessionLocal()
    try:
        reconcile_stuck_orders(db)
    finally:
        db.close()


def run_event_log_cleanup():
    from app.services.event_log_cleanup_service import cleanup_old_user_events
    db = SessionLocal()
    try:
        cleanup_old_user_events(db)
    finally:
        db.close()


def run_diagnostic_report_cleanup():
    from app.services.diagnostic_report_cleanup_service import cleanup_old_diagnostic_reports
    db = SessionLocal()
    try:
        cleanup_old_diagnostic_reports(db)
    finally:
        db.close()


if _acquire_scheduler_lock():
    scheduler = BackgroundScheduler()
    # ⏰ Runs every 24 hours
    scheduler.add_job(run_expiry_check, "interval", hours=24)
    # ⏰ Order reconciliation (plan §6.4/§9) — checks Razorpay orders stuck
    # in "created" status for longer than the grace period. Runs far more
    # frequently than the expiry check since this is real money potentially
    # sitting unresolved, not a routine status sweep.
    scheduler.add_job(run_order_reconciliation, "interval", minutes=15)
    # ⏰ user_event_logs retention — deletes breadcrumb rows older than 90
    # days (RETENTION_DAYS in event_log_cleanup_service.py). Same cadence as
    # the expiry check since this is routine housekeeping, not time-sensitive.
    scheduler.add_job(run_event_log_cleanup, "interval", hours=24)
    # ⏰ diagnostic_reports retention — deletes on-demand full-trail uploads
    # older than 14 days (RETENTION_DAYS in diagnostic_report_cleanup_service.py).
    # Much shorter than user_event_logs since a report is only useful while a
    # specific investigation is active.
    scheduler.add_job(run_diagnostic_report_cleanup, "interval", hours=24)
    scheduler.start()
    logger.info("Background scheduler started on this worker (advisory lock acquired).")
else:
    logger.info("Background scheduler not started on this worker (another worker holds the lock).")


# READY FOR HOSTING — target platform is Google Cloud Run (see
# Dockerfile: reads $PORT at runtime, the Cloud Run convention). An
# earlier "READY FOR AWS HOSTING" comment here was stale/inconsistent
# with the Dockerfile and docs/DOCKER_GUIDE.md, which have always
# targeted Cloud Run — corrected 2026-08-14.
