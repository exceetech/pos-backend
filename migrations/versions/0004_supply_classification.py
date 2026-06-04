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
    op.add_column('purchase_items',
        sa.Column('supply_classification', sa.String, nullable=False, server_default='TAXABLE')
    )

def downgrade():
    op.drop_column('purchase_items', 'supply_classification')
