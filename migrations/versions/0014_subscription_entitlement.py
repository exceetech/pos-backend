"""
Add Subscription.funding_order_id and Order.order_type — the two columns
needed by subscription_entitlement_service to (a) compute an upgrade
credit off what a shop ACTUALLY paid rather than plan list price, and
(b) record how each order was classified (fresh/renewal/upgrade/
downgrade/trial_convert) for later reporting.

Both columns are nullable and additive only — no existing row is
touched, no existing query breaks if this hasn't run yet (the
entitlement service treats a null funding_order_id as "no credit
available" rather than erroring), so this is safe to deploy ahead of or
behind the application code that starts writing these columns.

Revision ID: 0014_subscription_entitlement
Revises: 0013_update_plan_pricing
Create Date: 2026-08-05
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '0014_subscription_entitlement'
down_revision = '0013_update_plan_pricing'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "subscriptions",
        sa.Column("funding_order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column("order_type", sa.String(), nullable=True),
    )


def downgrade():
    op.drop_column("orders", "order_type")
    op.drop_column("subscriptions", "funding_order_id")
