"""
Add GSTR-1 v23 fields to gst_sales_invoice, gst_sales_invoice_items,
gst_sales_records, and shop_products tables.

Revision ID: 0003_gstr1_v23_fields
Revises: 0002_add_gst_columns
Create Date: 2026-05-20
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '0003_gstr1_v23_fields'
down_revision = '0002_add_gst_columns'
branch_labels = None
depends_on = None


def upgrade():
    # ----------------------------------------------------------------
    # gst_sales_invoice — 9 new invoice-level GSTR-1 fields
    # ----------------------------------------------------------------
    op.add_column('gst_sales_invoice',
        sa.Column('invoice_number', sa.String, nullable=True, server_default='')
    )
    op.add_column('gst_sales_invoice',
        sa.Column('invoice_date', sa.BigInteger, nullable=False, server_default='0')
    )
    op.add_column('gst_sales_invoice',
        sa.Column('reverse_charge', sa.String, nullable=False, server_default='N')
    )
    op.add_column('gst_sales_invoice',
        sa.Column('gstr_invoice_type', sa.String, nullable=False, server_default='Regular')
    )
    op.add_column('gst_sales_invoice',
        sa.Column('customer_state_code', sa.String, nullable=True)
    )
    op.add_column('gst_sales_invoice',
        sa.Column('ecommerce_gstin', sa.String, nullable=True)
    )
    op.add_column('gst_sales_invoice',
        sa.Column('ecommerce_operator_name', sa.String, nullable=True)
    )
    op.add_column('gst_sales_invoice',
        sa.Column('is_cancelled', sa.Boolean, nullable=False, server_default='false')
    )
    op.add_column('gst_sales_invoice',
        sa.Column('cancelled_at', sa.DateTime, nullable=True)
    )

    # ----------------------------------------------------------------
    # gst_sales_invoice_items — 4 new item-level GSTR-1 fields
    # ----------------------------------------------------------------
    op.add_column('gst_sales_invoice_items',
        sa.Column('cess_rate', sa.Float, nullable=False, server_default='0.0')
    )
    op.add_column('gst_sales_invoice_items',
        sa.Column('cess_amount', sa.Float, nullable=False, server_default='0.0')
    )
    op.add_column('gst_sales_invoice_items',
        sa.Column('uqc', sa.String, nullable=True)
    )
    op.add_column('gst_sales_invoice_items',
        sa.Column('hsn_description', sa.String, nullable=True)
    )

    # ----------------------------------------------------------------
    # gst_sales_records — 15 new GSTR-1 enrichment fields
    # ----------------------------------------------------------------
    op.add_column('gst_sales_records',
        sa.Column('customer_name', sa.String, nullable=True)
    )
    op.add_column('gst_sales_records',
        sa.Column('business_name', sa.String, nullable=True)
    )
    op.add_column('gst_sales_records',
        sa.Column('customer_phone', sa.String, nullable=True)
    )
    op.add_column('gst_sales_records',
        sa.Column('customer_state', sa.String, nullable=True)
    )
    op.add_column('gst_sales_records',
        sa.Column('customer_state_code', sa.String, nullable=True)
    )
    op.add_column('gst_sales_records',
        sa.Column('reverse_charge', sa.String, nullable=False, server_default='N')
    )
    op.add_column('gst_sales_records',
        sa.Column('gstr_invoice_type', sa.String, nullable=False, server_default='Regular')
    )
    op.add_column('gst_sales_records',
        sa.Column('ecommerce_gstin', sa.String, nullable=True)
    )
    op.add_column('gst_sales_records',
        sa.Column('ecommerce_operator_name', sa.String, nullable=True)
    )
    op.add_column('gst_sales_records',
        sa.Column('cess_rate', sa.Float, nullable=False, server_default='0.0')
    )
    op.add_column('gst_sales_records',
        sa.Column('cess_amount', sa.Float, nullable=False, server_default='0.0')
    )
    op.add_column('gst_sales_records',
        sa.Column('uqc', sa.String, nullable=True)
    )
    op.add_column('gst_sales_records',
        sa.Column('hsn_description', sa.String, nullable=True)
    )
    op.add_column('gst_sales_records',
        sa.Column('is_cancelled', sa.Boolean, nullable=False, server_default='false')
    )

    # ----------------------------------------------------------------
    # shop_products — 6 new GSTR-1 product master fields
    # ----------------------------------------------------------------
    op.add_column('shop_products',
        sa.Column('cgst_percentage', sa.Float, nullable=False, server_default='0.0')
    )
    op.add_column('shop_products',
        sa.Column('sgst_percentage', sa.Float, nullable=False, server_default='0.0')
    )
    op.add_column('shop_products',
        sa.Column('igst_percentage', sa.Float, nullable=False, server_default='0.0')
    )
    op.add_column('shop_products',
        sa.Column('official_uqc', sa.String, nullable=True)
    )
    op.add_column('shop_products',
        sa.Column('hsn_description', sa.String, nullable=True)
    )
    op.add_column('shop_products',
        sa.Column('cess_rate', sa.Float, nullable=False, server_default='0.0')
    )


def downgrade():
    # ----------------------------------------------------------------
    # shop_products
    # ----------------------------------------------------------------
    op.drop_column('shop_products', 'cess_rate')
    op.drop_column('shop_products', 'hsn_description')
    op.drop_column('shop_products', 'official_uqc')
    op.drop_column('shop_products', 'igst_percentage')
    op.drop_column('shop_products', 'sgst_percentage')
    op.drop_column('shop_products', 'cgst_percentage')

    # ----------------------------------------------------------------
    # gst_sales_records
    # ----------------------------------------------------------------
    op.drop_column('gst_sales_records', 'is_cancelled')
    op.drop_column('gst_sales_records', 'hsn_description')
    op.drop_column('gst_sales_records', 'uqc')
    op.drop_column('gst_sales_records', 'cess_amount')
    op.drop_column('gst_sales_records', 'cess_rate')
    op.drop_column('gst_sales_records', 'ecommerce_operator_name')
    op.drop_column('gst_sales_records', 'ecommerce_gstin')
    op.drop_column('gst_sales_records', 'gstr_invoice_type')
    op.drop_column('gst_sales_records', 'reverse_charge')
    op.drop_column('gst_sales_records', 'customer_state_code')
    op.drop_column('gst_sales_records', 'customer_state')
    op.drop_column('gst_sales_records', 'customer_phone')
    op.drop_column('gst_sales_records', 'business_name')
    op.drop_column('gst_sales_records', 'customer_name')

    # ----------------------------------------------------------------
    # gst_sales_invoice_items
    # ----------------------------------------------------------------
    op.drop_column('gst_sales_invoice_items', 'hsn_description')
    op.drop_column('gst_sales_invoice_items', 'uqc')
    op.drop_column('gst_sales_invoice_items', 'cess_amount')
    op.drop_column('gst_sales_invoice_items', 'cess_rate')

    # ----------------------------------------------------------------
    # gst_sales_invoice
    # ----------------------------------------------------------------
    op.drop_column('gst_sales_invoice', 'cancelled_at')
    op.drop_column('gst_sales_invoice', 'is_cancelled')
    op.drop_column('gst_sales_invoice', 'ecommerce_operator_name')
    op.drop_column('gst_sales_invoice', 'ecommerce_gstin')
    op.drop_column('gst_sales_invoice', 'customer_state_code')
    op.drop_column('gst_sales_invoice', 'gstr_invoice_type')
    op.drop_column('gst_sales_invoice', 'reverse_charge')
    op.drop_column('gst_sales_invoice', 'invoice_date')
    op.drop_column('gst_sales_invoice', 'invoice_number')
