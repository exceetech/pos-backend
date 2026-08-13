"""
Onboarding + subscription tier/trial columns on shops/subscriptions,
with a one-time backfill for shops/subscriptions that predate them.

Ported from app/main.py's _add_onboarding_and_subscription_tier_columns() as part of consolidating the
28 ad-hoc startup ALTER functions into real, ordered Alembic migrations.
The logic below is unchanged from the original function — only the
connection source changed (op.get_bind() instead of a fresh
engine.connect()), so this migration is exactly as idempotent-safe as
the original was, and safe to run against a database that already has
some or all of these columns/tables.

Revision ID: 0043_add_onboarding_and_subscription_tier_columns
Revises: 0042_add_purchase_return_variance_column
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = '0043_add_onboarding_and_subscription_tier_columns'
down_revision = '0042_add_purchase_return_variance_column'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = inspect(conn)

    if "shops" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("shops")}

        def _add(col, ddl):
            if col not in cols:
                conn.execute(text(f"ALTER TABLE shops ADD COLUMN {ddl}"))
                cols.add(col)

        _add("onboarding_completed_at", "onboarding_completed_at TIMESTAMP NULL")
        _add("onboarding_subscription_done", "onboarding_subscription_done BOOLEAN NOT NULL DEFAULT FALSE")
        _add("onboarding_shop_info_done", "onboarding_shop_info_done BOOLEAN NOT NULL DEFAULT FALSE")
        _add("onboarding_billing_done", "onboarding_billing_done BOOLEAN NOT NULL DEFAULT FALSE")
        _add("onboarding_terms_done", "onboarding_terms_done BOOLEAN NOT NULL DEFAULT FALSE")
        _add("terms_accepted_at", "terms_accepted_at TIMESTAMP NULL")
        _add("terms_version", "terms_version VARCHAR NULL")
        _add("has_used_trial", "has_used_trial BOOLEAN NOT NULL DEFAULT FALSE")

        conn.execute(text(
            "UPDATE shops SET "
            "onboarding_completed_at = created_at, "
            "onboarding_subscription_done = TRUE, "
            "onboarding_shop_info_done = TRUE, "
            "onboarding_billing_done = TRUE, "
            "onboarding_terms_done = TRUE, "
            "terms_accepted_at = COALESCE(terms_accepted_at, created_at) "
            "WHERE onboarding_completed_at IS NULL"
        ))

    if "subscriptions" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("subscriptions")}

        if "tier" not in cols:
            conn.execute(text("ALTER TABLE subscriptions ADD COLUMN tier VARCHAR NULL"))
            cols.add("tier")
        if "trial_started_at" not in cols:
            conn.execute(text("ALTER TABLE subscriptions ADD COLUMN trial_started_at TIMESTAMP NULL"))
            cols.add("trial_started_at")
        if "funding_order_id" not in cols:
            conn.execute(text(
                "ALTER TABLE subscriptions ADD COLUMN funding_order_id INTEGER NULL REFERENCES orders(id)"
            ))
            cols.add("funding_order_id")

        conn.execute(text(
            "UPDATE subscriptions SET tier = 'premium' WHERE tier IS NULL"
        ))


def downgrade():
    # Not reversed: the backfill above is a one-time data decision
    # (assume-premium for pre-existing rows), not something that can be
    # safely un-guessed, and dropping these columns would break the
    # onboarding/subscription-tier features outright rather than restoring
    # old behavior. Restore from backup if full reversal is required.
    pass
