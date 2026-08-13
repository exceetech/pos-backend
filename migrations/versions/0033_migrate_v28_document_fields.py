"""
v28 — supply_classification on shop_products/gst_sales_invoice_items;
document_type/nature/series on gst_sales_invoice.

Ported from app/main.py's _migrate_v28() as part of consolidating the
28 ad-hoc startup ALTER functions into real, ordered Alembic migrations.
The logic below is unchanged from the original function — only the
connection source changed (op.get_bind() instead of a fresh
engine.connect()), so this migration is exactly as idempotent-safe as
the original was, and safe to run against a database that already has
some or all of these columns/tables.

Revision ID: 0033_migrate_v28_document_fields
Revises: 0032_migrate_v27_credit_notes_supply_type
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = '0033_migrate_v28_document_fields'
down_revision = '0032_migrate_v27_credit_notes_supply_type'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)

    if "shop_products" in inspector.get_table_names():
        cols = {c["name"]: c for c in inspector.get_columns("shop_products")}
        if "supply_classification" not in cols:
            conn.execute(text("ALTER TABLE shop_products ADD COLUMN supply_classification VARCHAR NOT NULL DEFAULT 'TAXABLE'"))

    if "gst_sales_invoice_items" in inspector.get_table_names():
        cols = {c["name"]: c for c in inspector.get_columns("gst_sales_invoice_items")}
        if "supply_classification" not in cols:
            conn.execute(text("ALTER TABLE gst_sales_invoice_items ADD COLUMN supply_classification VARCHAR NOT NULL DEFAULT 'TAXABLE'"))

    if "gst_sales_invoice" in inspector.get_table_names():
        cols = {c["name"]: c for c in inspector.get_columns("gst_sales_invoice")}
        if "document_type" not in cols:
            conn.execute(text("ALTER TABLE gst_sales_invoice ADD COLUMN document_type VARCHAR NULL"))
        if "document_nature" not in cols:
            conn.execute(text("ALTER TABLE gst_sales_invoice ADD COLUMN document_nature VARCHAR NULL"))
        if "document_series" not in cols:
            conn.execute(text("ALTER TABLE gst_sales_invoice ADD COLUMN document_series VARCHAR NULL"))


def downgrade():
    conn = op.get_bind()
    conn.execute(text("ALTER TABLE gst_sales_invoice DROP COLUMN IF EXISTS document_series"))
    conn.execute(text("ALTER TABLE gst_sales_invoice DROP COLUMN IF EXISTS document_nature"))
    conn.execute(text("ALTER TABLE gst_sales_invoice DROP COLUMN IF EXISTS document_type"))
    conn.execute(text("ALTER TABLE gst_sales_invoice_items DROP COLUMN IF EXISTS supply_classification"))
    conn.execute(text("ALTER TABLE shop_products DROP COLUMN IF EXISTS supply_classification"))
