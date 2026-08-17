"""
Adds `is_sellable` to shop_products for the Assets feature.

Purchase lines with ITC eligibility "Capital goods" / "Input services"
still create a ShopProduct row (asset record-keeping) but must not be
sellable — no stock, excluded from the billing/POS catalog. Existing
rows default to true (sellable) so today's behaviour is unaffected;
only new purchases (and edited purchases going through the app's
warn-before-switch flow) ever write false here.

Idempotent (checks column existence first), safe to re-run.

Revision ID: 0049_add_shop_products_is_sellable
Revises: 0048_add_store_gst_profile_address
Create Date: 2026-08-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0049_add_shop_products_is_sellable"
down_revision = "0048_add_store_gst_profile_address"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    existing_columns = {c["name"] for c in inspect(conn).get_columns("shop_products")}
    if "is_sellable" in existing_columns:
        return
    op.add_column(
        "shop_products",
        sa.Column("is_sellable", sa.Boolean(), nullable=False, server_default="true"),
    )


def downgrade():
    conn = op.get_bind()
    existing_columns = {c["name"] for c in inspect(conn).get_columns("shop_products")}
    if "is_sellable" not in existing_columns:
        return
    op.drop_column("shop_products", "is_sellable")
