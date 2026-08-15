"""
Add hsn_code and default_gst_rate to shop_products
Revision ID: 0002_add_gst_columns
Revises: 0001_gst_module
Create Date: 2026-04-28
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '0002_add_gst_columns'
down_revision = '0001_gst_module'
branch_labels = None
depends_on = None


def upgrade():
    # Guarded (2026-08-15): 0001 already adds these same two columns to
    # shop_products (this migration duplicates that — a pre-existing
    # issue independent of the fresh-DB baseline fix), and the baseline
    # migration (0000_baseline_schema) also creates shop_products already
    # containing them. Existence check makes this a safe no-op either way.
    from sqlalchemy import inspect
    existing = {c["name"] for c in inspect(op.get_bind()).get_columns("shop_products")}
    if "hsn_code" not in existing:
        op.add_column('shop_products',
            sa.Column('hsn_code', sa.String, nullable=True)
        )
    if "default_gst_rate" not in existing:
        op.add_column('shop_products',
            sa.Column('default_gst_rate', sa.Float, nullable=True, server_default='0.0')
        )


def downgrade():
    # Remove GST columns from shop_products
    op.drop_column('shop_products', 'hsn_code')
    op.drop_column('shop_products', 'default_gst_rate')