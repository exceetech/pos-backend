"""
Performance audit: add missing indexes on frequently-queried foreign key
columns. These columns had no index at all — every lookup by shop_id
(the single most common filter in this multi-tenant app) or by these
other FKs was doing a full table scan instead of an index lookup. Fine
with a handful of test rows, increasingly costly as real shop data
accumulates.

Idempotent (CREATE INDEX IF NOT EXISTS / DROP INDEX IF EXISTS), safe to
re-run.

Revision ID: 0044_add_missing_fk_indexes
Revises: 0043_add_onboarding_and_subscription_tier_columns
Create Date: 2026-08-13
"""
from alembic import op
from sqlalchemy import text

revision = "0044_add_missing_fk_indexes"
down_revision = "0043_add_onboarding_and_subscription_tier_columns"
branch_labels = None
depends_on = None

INDEXES = [
    ("ix_shop_products_shop_id", "shop_products", "shop_id"),
    ("ix_shop_products_global_product_id", "shop_products", "global_product_id"),
    ("ix_inventory_shop_id", "inventory", "shop_id"),
    ("ix_subscriptions_shop_id", "subscriptions", "shop_id"),
    ("ix_coupon_redemptions_coupon_id", "coupon_redemptions", "coupon_id"),
    ("ix_coupon_redemptions_shop_id", "coupon_redemptions", "shop_id"),
    ("ix_global_product_variants_created_by_shop_id", "global_product_variants", "created_by_shop_id"),
    ("ix_inventory_logs_shop_id", "inventory_logs", "shop_id"),
    ("ix_inventory_logs_product_id", "inventory_logs", "product_id"),
]


def upgrade():
    conn = op.get_bind()
    from sqlalchemy import inspect
    existing_tables = set(inspect(conn).get_table_names())
    for index_name, table_name, column_name in INDEXES:
        if table_name not in existing_tables:
            continue
        conn.execute(text(
            f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({column_name})"
        ))


def downgrade():
    conn = op.get_bind()
    for index_name, _table_name, _column_name in INDEXES:
        conn.execute(text(f"DROP INDEX IF EXISTS {index_name}"))
