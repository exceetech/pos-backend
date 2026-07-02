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
    # We will add server_default='false' to ensure existing rows get false
    op.add_column('shop_products', sa.Column('is_tax_inclusive', sa.Boolean(), server_default='false', nullable=False))

def downgrade() -> None:
    op.drop_column('shop_products', 'is_tax_inclusive')
