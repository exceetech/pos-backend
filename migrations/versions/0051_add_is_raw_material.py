"""
Adds `is_raw_material` to shop_products and purchase_items.

Raw-material toggle: a purchase line can be tagged a genuine raw material
(e.g. flour, sugar) rather than an eligibility-driven asset (Capital
goods / Input services). It shares the same asset-like inventory gating
as those (no stock, excluded from the sellable billing/POS catalog) but
is an independent tag, purely so the Assets screen can label the row
"Raw material" instead of "Asset". GST eligibility (eligibility_for_itc)
is completely unaffected. Existing rows default to false.

Idempotent (checks column existence first), safe to re-run.

Revision ID: 0051_add_is_raw_material
Revises: 0050_drop_purchases_eligibility_for_itc
Create Date: 2026-08-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0051_add_is_raw_material"
down_revision = "0050_drop_purchases_eligibility_for_itc"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    shop_products_columns = {c["name"] for c in inspect(conn).get_columns("shop_products")}
    if "is_raw_material" not in shop_products_columns:
        op.add_column(
            "shop_products",
            sa.Column("is_raw_material", sa.Boolean(), nullable=False, server_default="false"),
        )

    purchase_items_columns = {c["name"] for c in inspect(conn).get_columns("purchase_items")}
    if "is_raw_material" not in purchase_items_columns:
        op.add_column(
            "purchase_items",
            sa.Column("is_raw_material", sa.Boolean(), nullable=False, server_default="false"),
        )


def downgrade():
    conn = op.get_bind()

    purchase_items_columns = {c["name"] for c in inspect(conn).get_columns("purchase_items")}
    if "is_raw_material" in purchase_items_columns:
        op.drop_column("purchase_items", "is_raw_material")

    shop_products_columns = {c["name"] for c in inspect(conn).get_columns("shop_products")}
    if "is_raw_material" in shop_products_columns:
        op.drop_column("shop_products", "is_raw_material")
