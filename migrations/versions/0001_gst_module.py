"""
GST Module Production Migration
Revision ID: 0001_gst_module
Revises: (base)
Create Date: 2026-04-28

What this migration does:
1. Creates store_gst_profile table
2. Creates gst_sales_records table (per-line-item GST breakdown)
3. Creates gst_purchase_records table (purchase/expense GST)
4. Adds hsn_code, default_gst_rate to shop_products
5. Adds legal_name, trade_name, gst_scheme, state_code, registration_type to shops (via gst_profile)
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '0001_gst_module'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ============================================================
    # 1. store_gst_profile
    # ============================================================
    op.create_table(
        'store_gst_profile',
        sa.Column('id', sa.String, primary_key=True),
        sa.Column('shop_id', sa.Integer, sa.ForeignKey('shops.id'), nullable=False, unique=True),
        sa.Column('gstin', sa.String, nullable=False),
        sa.Column('legal_name', sa.String, default=''),
        sa.Column('trade_name', sa.String, default=''),
        sa.Column('gst_scheme', sa.String, default=''),
        sa.Column('registration_type', sa.String, default=''),
        sa.Column('state_code', sa.String, default=''),
        sa.Column('sync_status', sa.String, default='pending'),
        sa.Column('device_id', sa.String, default=''),
        sa.Column('created_at', sa.DateTime),
        sa.Column('updated_at', sa.DateTime),
    )
    op.create_index('ix_store_gst_profile_shop_id', 'store_gst_profile', ['shop_id'])

    # ============================================================
    # 2. gst_sales_records
    # ============================================================
    op.create_table(
        'gst_sales_records',
        sa.Column('id', sa.String, primary_key=True),
        sa.Column('shop_id', sa.Integer, sa.ForeignKey('shops.id'), nullable=False),
        sa.Column('invoice_number', sa.String, nullable=False),
        sa.Column('invoice_date', sa.DateTime, nullable=False),
        sa.Column('customer_type', sa.String, nullable=False),
        sa.Column('customer_gstin', sa.String, nullable=True),
        sa.Column('place_of_supply', sa.String, nullable=False),
        sa.Column('supply_type', sa.String, nullable=False),
        sa.Column('hsn_code', sa.String, nullable=False),
        sa.Column('product_name', sa.String, nullable=False),
        sa.Column('quantity', sa.Float, nullable=False),
        sa.Column('unit', sa.String, default='piece'),
        sa.Column('taxable_value', sa.Float, nullable=False),
        sa.Column('gst_rate', sa.Float, nullable=False),
        sa.Column('cgst_amount', sa.Float, default=0.0),
        sa.Column('sgst_amount', sa.Float, default=0.0),
        sa.Column('igst_amount', sa.Float, default=0.0),
        sa.Column('total_amount', sa.Float, nullable=False),
        sa.Column('sync_status', sa.String, default='pending'),
        sa.Column('device_id', sa.String, default=''),
        sa.Column('created_at', sa.DateTime),
        sa.Column('updated_at', sa.DateTime),
    )
    op.create_index('ix_gst_sales_records_shop_id', 'gst_sales_records', ['shop_id'])
    op.create_index('ix_gst_sales_records_invoice_number', 'gst_sales_records', ['invoice_number'])
    op.create_index('ix_gst_sales_records_invoice_date', 'gst_sales_records', ['invoice_date'])
    op.create_index('ix_gst_sales_records_hsn_code', 'gst_sales_records', ['hsn_code'])
    op.create_index('ix_gst_sales_records_sync_status', 'gst_sales_records', ['sync_status'])

    # ============================================================
    # 3. gst_purchase_records
    # ============================================================
    op.create_table(
        'gst_purchase_records',
        sa.Column('id', sa.String, primary_key=True),
        sa.Column('shop_id', sa.Integer, sa.ForeignKey('shops.id'), nullable=False),
        sa.Column('supplier_gstin', sa.String, nullable=True),
        sa.Column('invoice_number', sa.String, nullable=False),
        sa.Column('invoice_date', sa.DateTime, nullable=False),
        sa.Column('expense_type', sa.String, nullable=False),
        sa.Column('hsn_sac_code', sa.String, nullable=False),
        sa.Column('description', sa.String, default=''),
        sa.Column('taxable_value', sa.Float, nullable=False),
        sa.Column('gst_rate', sa.Float, nullable=False),
        sa.Column('cgst_amount', sa.Float, default=0.0),
        sa.Column('sgst_amount', sa.Float, default=0.0),
        sa.Column('igst_amount', sa.Float, default=0.0),
        sa.Column('total_amount', sa.Float, nullable=False),
        sa.Column('sync_status', sa.String, default='pending'),
        sa.Column('device_id', sa.String, default=''),
        sa.Column('created_at', sa.DateTime),
        sa.Column('updated_at', sa.DateTime),
    )
    op.create_index('ix_gst_purchase_records_shop_id', 'gst_purchase_records', ['shop_id'])
    op.create_index('ix_gst_purchase_records_invoice_number', 'gst_purchase_records', ['invoice_number'])
    op.create_index('ix_gst_purchase_records_invoice_date', 'gst_purchase_records', ['invoice_date'])
    op.create_index('ix_gst_purchase_records_sync_status', 'gst_purchase_records', ['sync_status'])

    # ============================================================
    # 4. Add GST columns to shop_products (safe: nullable with default)
    # ============================================================
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

    # Drop new tables (in reverse foreign-key order)
    op.drop_index('ix_gst_purchase_records_sync_status', table_name='gst_purchase_records')
    op.drop_index('ix_gst_purchase_records_invoice_date', table_name='gst_purchase_records')
    op.drop_index('ix_gst_purchase_records_invoice_number', table_name='gst_purchase_records')
    op.drop_index('ix_gst_purchase_records_shop_id', table_name='gst_purchase_records')
    op.drop_table('gst_purchase_records')

    op.drop_index('ix_gst_sales_records_sync_status', table_name='gst_sales_records')
    op.drop_index('ix_gst_sales_records_hsn_code', table_name='gst_sales_records')
    op.drop_index('ix_gst_sales_records_invoice_date', table_name='gst_sales_records')
    op.drop_index('ix_gst_sales_records_invoice_number', table_name='gst_sales_records')
    op.drop_index('ix_gst_sales_records_shop_id', table_name='gst_sales_records')
    op.drop_table('gst_sales_records')

    op.drop_index('ix_store_gst_profile_shop_id', table_name='store_gst_profile')
    op.drop_table('store_gst_profile')
