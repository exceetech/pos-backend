"""
GSTR-1 support columns across shop_products, gst_sales_invoice(+items),
bills and credit_transactions, plus their lookup indexes.

Ported from app/main.py's _add_gstr_support_columns() as part of consolidating the
28 ad-hoc startup ALTER functions into real, ordered Alembic migrations.
The logic below is unchanged from the original function — only the
connection source changed (op.get_bind() instead of a fresh
engine.connect()), so this migration is exactly as idempotent-safe as
the original was, and safe to run against a database that already has
some or all of these columns/tables.

Revision ID: 0022_add_gstr_support_columns
Revises: 0021_add_delta_cursor_columns
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = '0022_add_gstr_support_columns'
down_revision = '0021_add_delta_cursor_columns'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    def _add_col(table_name, existing, column_name, ddl):
        if column_name not in existing:
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {ddl}"))
            existing.add(column_name)

    columns_by_table = {
        "shop_products": [
            ("cgst_percentage", "cgst_percentage DOUBLE PRECISION NOT NULL DEFAULT 0.0"),
            ("sgst_percentage", "sgst_percentage DOUBLE PRECISION NOT NULL DEFAULT 0.0"),
            ("igst_percentage", "igst_percentage DOUBLE PRECISION NOT NULL DEFAULT 0.0"),
            ("official_uqc", "official_uqc VARCHAR NULL"),
            ("hsn_description", "hsn_description VARCHAR NULL"),
            ("cess_rate", "cess_rate DOUBLE PRECISION NOT NULL DEFAULT 0.0"),
            ("supply_classification", "supply_classification VARCHAR NOT NULL DEFAULT 'TAXABLE'"),
            ("category", "category VARCHAR NULL DEFAULT ''"),
        ],
        "gst_sales_invoice": [
            ("invoice_number", "invoice_number VARCHAR NULL DEFAULT ''"),
            ("invoice_date", "invoice_date BIGINT NULL DEFAULT 0"),
            ("reverse_charge", "reverse_charge VARCHAR NOT NULL DEFAULT 'N'"),
            ("gstr_invoice_type", "gstr_invoice_type VARCHAR NOT NULL DEFAULT 'Regular'"),
            ("customer_state_code", "customer_state_code VARCHAR NULL"),
            ("ecommerce_gstin", "ecommerce_gstin VARCHAR NULL"),
            ("ecommerce_operator_name", "ecommerce_operator_name VARCHAR NULL"),
            ("eco_nature_of_supply", "eco_nature_of_supply VARCHAR NULL"),
            ("eco_document_type", "eco_document_type VARCHAR NULL"),
            ("eco_supplier_gstin", "eco_supplier_gstin VARCHAR NULL"),
            ("eco_supplier_name", "eco_supplier_name VARCHAR NULL"),
            ("eco_recipient_gstin", "eco_recipient_gstin VARCHAR NULL"),
            ("eco_recipient_name", "eco_recipient_name VARCHAR NULL"),
            ("eco_role", "eco_role VARCHAR NULL"),
            ("is_cancelled", "is_cancelled BOOLEAN NOT NULL DEFAULT FALSE"),
            ("cancelled_at", "cancelled_at TIMESTAMP NULL"),
        ],
        "gst_sales_invoice_items": [
            ("cess_rate", "cess_rate DOUBLE PRECISION NOT NULL DEFAULT 0.0"),
            ("cess_amount", "cess_amount DOUBLE PRECISION NOT NULL DEFAULT 0.0"),
            ("uqc", "uqc VARCHAR NULL"),
            ("hsn_description", "hsn_description VARCHAR NULL"),
        ],
        "bills": [
            ("client_bill_id",  "client_bill_id INTEGER NULL"),
            ("client_device_id","client_device_id VARCHAR NULL"),
            ("is_cancelled",  "is_cancelled BOOLEAN NOT NULL DEFAULT FALSE"),
            ("cancelled_at",  "cancelled_at TIMESTAMP NULL"),
            ("created_at",    "created_at TIMESTAMP NULL"),
            ("active",        "active BOOLEAN DEFAULT TRUE"),
            ("credit_account_id", "credit_account_id INTEGER NULL"),
        ],
        "credit_transactions": [
            ("source_doc", "source_doc VARCHAR NULL"),
        ],
    }

    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())

    for table_name, column_defs in columns_by_table.items():
        if table_name not in existing_tables:
            continue
        existing = {c["name"] for c in inspector.get_columns(table_name)}
        for column_name, ddl in column_defs:
            _add_col(table_name, existing, column_name, ddl)

    if "bills" in existing_tables:
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_bills_client_key "
            "ON bills (shop_id, client_device_id, client_bill_id)"
        ))
    if "credit_transactions" in existing_tables:
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_credit_transactions_source_doc "
            "ON credit_transactions (shop_id, source_doc)"
        ))


def downgrade():
    # Additive-only migration touching many tables — deliberately not
    # reversed column-by-column (high risk of dropping columns other, later
    # migrations also depend on). Restore from a pre-upgrade backup if this
    # needs to be undone.
    pass
