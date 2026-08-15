"""add is_tax_inclusive to shop_products

Revision ID: 0009_is_tax_inclusive
Revises: 0007_bill_cancellation
Create Date: 2026-07-02 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0009_is_tax_inclusive'
down_revision = '0007_bill_cancellation'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Guarded (2026-08-15): shop_products is created by the baseline
    # migration (0000_baseline_schema) from today's model, which already
    # includes this column.
    from sqlalchemy import inspect
    existing = {c["name"] for c in inspect(op.get_bind()).get_columns("shop_products")}
    if "is_tax_inclusive" not in existing:
        # We will add server_default='false' to ensure existing rows get false
        op.add_column('shop_products', sa.Column('is_tax_inclusive', sa.Boolean(), server_default='false', nullable=False))

def downgrade() -> None:
    op.drop_column('shop_products', 'is_tax_inclusive')
