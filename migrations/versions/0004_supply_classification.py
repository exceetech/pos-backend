"""
Add supply_classification field to purchase_items table.

Revision ID: 0004_supply_classification
Revises: 0003_gstr1_v23_fields
Create Date: 2026-06-04
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '0004_supply_classification'
down_revision = '0003_gstr1_v23_fields'
branch_labels = None
depends_on = None


def upgrade():
    # Guarded (2026-08-15): purchase_items is created by the baseline
    # migration (0000_baseline_schema) from today's model, which already
    # includes this column — existence check makes this a safe no-op on
    # a fresh database, still adds it normally on an existing one.
    from sqlalchemy import inspect
    existing = {c["name"] for c in inspect(op.get_bind()).get_columns("purchase_items")}
    if "supply_classification" not in existing:
        op.add_column('purchase_items',
            sa.Column('supply_classification', sa.String, nullable=False, server_default='TAXABLE')
        )

def downgrade():
    op.drop_column('purchase_items', 'supply_classification')
