"""
Adds brand (nullable) to global_product_variants — lets the shared
global catalog carry a brand alongside name/variant, matching the
Android app's local Product.brand field (Part 1) and the unified
Name·Brand·Type search box (Part 2). Optional everywhere: existing
callers that don't send brand keep working unchanged.

Idempotent (checks column existence first), safe to re-run.

Revision ID: 0056_add_global_variant_brand
Revises: 0055_add_bill_qr_close_by
Create Date: 2026-09-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0056_add_global_variant_brand"
down_revision = "0055_add_bill_qr_close_by"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    columns = {c["name"] for c in inspect(conn).get_columns("global_product_variants")}

    if "brand" not in columns:
        op.add_column(
            "global_product_variants", sa.Column("brand", sa.String(), nullable=True)
        )


def downgrade():
    conn = op.get_bind()
    columns = {c["name"] for c in inspect(conn).get_columns("global_product_variants")}

    if "brand" in columns:
        op.drop_column("global_product_variants", "brand")
