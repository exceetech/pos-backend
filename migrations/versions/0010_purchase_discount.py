"""add discount_amount to purchase_items

Revision ID: 0010_purchase_discount
Revises: 0009_is_tax_inclusive
Create Date: 2026-07-03 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0010_purchase_discount'
down_revision = '0009_is_tax_inclusive'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('purchase_items', sa.Column('discount_amount', sa.Float(), server_default='0.0', nullable=False))

def downgrade() -> None:
    op.drop_column('purchase_items', 'discount_amount')
