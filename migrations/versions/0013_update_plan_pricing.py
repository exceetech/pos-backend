"""
Update Base and Premium plan pricing.

Base moves from free-forever (price_paise=0, duration_days=36500) to a
paid monthly plan at ₹699. Premium moves from ₹299/month to ₹999/month.
Both now go through the normal create-order/Razorpay checkout path like
any other paid tier — nothing in subscription_pricing_service or
dependencies.py special-cases price_paise==0, so no other code needed
to change for this.

This is a data-only migration: it updates the two existing plan rows by
plan_code (base_monthly, premium_monthly) if they're already present —
the app/main.py seeder is idempotent and only inserts rows that don't
exist yet, so an already-deployed DB needs this explicit update instead.
No-op on a fresh DB where the seeder itself already inserts the new
prices.

Revision ID: 0013_update_plan_pricing
Revises: 0012_purchase_creditnote_device_id
Create Date: 2026-08-02
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '0013_update_plan_pricing'
down_revision = '0012_purchase_creditnote_device_id'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        sa.text(
            "UPDATE plans SET price_paise = 69900, duration_days = 30 "
            "WHERE plan_code = 'base_monthly'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE plans SET price_paise = 99900 "
            "WHERE plan_code = 'premium_monthly'"
        )
    )


def downgrade():
    op.execute(
        sa.text(
            "UPDATE plans SET price_paise = 0, duration_days = 36500 "
            "WHERE plan_code = 'base_monthly'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE plans SET price_paise = 29900 "
            "WHERE plan_code = 'premium_monthly'"
        )
    )
