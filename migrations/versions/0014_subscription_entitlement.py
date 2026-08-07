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


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column_name in {c["name"] for c in inspector.get_columns(table_name)}


def upgrade():
    # Guarded rather than a flat add_column: a prior partial run (or manual
    # fix) can leave one of these two columns already in place. Postgres DDL
    # is transactional, so the original unconditional version failed and
    # rolled back BOTH columns the moment it hit whichever one already
    # existed — meaning the other, still-missing column never got added
    # either, and alembic_version stayed on 0013 forever. Checking first
    # makes this migration re-runnable regardless of which column (if any)
    # is already there.
    if not _has_column("subscriptions", "funding_order_id"):
        op.add_column(
            "subscriptions",
            sa.Column("funding_order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=True),
        )
    if not _has_column("orders", "order_type"):
        op.add_column(
            "orders",
            sa.Column("order_type", sa.String(), nullable=True),
        )


def downgrade():
    if _has_column("orders", "order_type"):
        op.drop_column("orders", "order_type")
    if _has_column("subscriptions", "funding_order_id"):
        op.drop_column("subscriptions", "funding_order_id")
