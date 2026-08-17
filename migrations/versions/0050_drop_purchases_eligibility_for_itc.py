"""
Drops the unused Purchase-header `eligibility_for_itc` column.

GST reporting was moved to read each PurchaseItem line's own eligibility
instead of this header-level copy, and the Android UI that used to set
it was removed — the field has been dead weight ever since, hardcoded to
"Inputs" purely to satisfy the not-null column. `purchase_items.eligibility_for_itc`
is untouched; it's a different column on a different table and is still
load-bearing (drives GST reporting and asset/sellable inventory gating).

Existing rows have real (now-meaningless) values in this column — this
just drops it, no data migration needed.

Idempotent (checks column existence first), safe to re-run.

Revision ID: 0050_drop_purchases_eligibility_for_itc
Revises: 0049_add_shop_products_is_sellable
Create Date: 2026-08-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0050_drop_purchases_eligibility_for_itc"
down_revision = "0049_add_shop_products_is_sellable"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    existing_columns = {c["name"] for c in inspect(conn).get_columns("purchases")}
    if "eligibility_for_itc" not in existing_columns:
        return
    op.drop_column("purchases", "eligibility_for_itc")


def downgrade():
    conn = op.get_bind()
    existing_columns = {c["name"] for c in inspect(conn).get_columns("purchases")}
    if "eligibility_for_itc" in existing_columns:
        return
    op.add_column(
        "purchases",
        sa.Column("eligibility_for_itc", sa.String(), nullable=False, server_default="Inputs"),
    )
