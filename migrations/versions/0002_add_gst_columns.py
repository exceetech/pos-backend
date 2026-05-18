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
    # Add GST columns to shop_products
    op.add_column('shop_products',
        sa.Column('hsn_code', sa.String, nullable=True)
    )
    op.add_column('shop_products',
        sa.Column('default_gst_rate', sa.Float, nullable=True, server_default='0.0')
    )


def downgrade():
    # Remove GST columns from shop_products
    op.drop_column('shop_products', 'hsn_code')
    op.drop_column('shop_products', 'default_gst_rate')