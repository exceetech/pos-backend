"""
v33 — GSTR ITC + document-reason fields on purchase_returns.

Ported from app/main.py's _migrate_v33() as part of consolidating the
28 ad-hoc startup ALTER functions into real, ordered Alembic migrations.
The logic below is unchanged from the original function — only the
connection source changed (op.get_bind() instead of a fresh
engine.connect()), so this migration is exactly as idempotent-safe as
the original was, and safe to run against a database that already has
some or all of these columns/tables.

Revision ID: 0038_migrate_v33_purchase_returns_gstr_fields
Revises: 0037_migrate_v32_purchase_returns_document_fields
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = '0038_migrate_v33_purchase_returns_gstr_fields'
down_revision = '0037_migrate_v32_purchase_returns_document_fields'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    if "purchase_returns" not in inspect(conn).get_table_names():
        return
    cols = {c["name"]: c for c in inspect(conn).get_columns("purchase_returns")}

    cols_to_add = {
        "pre_gst": "ALTER TABLE purchase_returns ADD COLUMN pre_gst VARCHAR NOT NULL DEFAULT 'N'",
        "reason_for_issuing_document": "ALTER TABLE purchase_returns ADD COLUMN reason_for_issuing_document VARCHAR NOT NULL DEFAULT 'Purchase return'",
        "note_refund_voucher_value": "ALTER TABLE purchase_returns ADD COLUMN note_refund_voucher_value DOUBLE PRECISION NOT NULL DEFAULT 0.0",
        "rate": "ALTER TABLE purchase_returns ADD COLUMN rate DOUBLE PRECISION NOT NULL DEFAULT 0.0",
        "eligibility_for_itc": "ALTER TABLE purchase_returns ADD COLUMN eligibility_for_itc VARCHAR NOT NULL DEFAULT 'Inputs'",
        "availed_itc_integrated_tax": "ALTER TABLE purchase_returns ADD COLUMN availed_itc_integrated_tax DOUBLE PRECISION NOT NULL DEFAULT 0.0",
        "availed_itc_central_tax": "ALTER TABLE purchase_returns ADD COLUMN availed_itc_central_tax DOUBLE PRECISION NOT NULL DEFAULT 0.0",
        "availed_itc_state_tax": "ALTER TABLE purchase_returns ADD COLUMN availed_itc_state_tax DOUBLE PRECISION NOT NULL DEFAULT 0.0",
        "availed_itc_cess": "ALTER TABLE purchase_returns ADD COLUMN availed_itc_cess DOUBLE PRECISION NOT NULL DEFAULT 0.0",
        "invoice_type": "ALTER TABLE purchase_returns ADD COLUMN invoice_type VARCHAR NOT NULL DEFAULT 'Regular'",
        "place_of_supply_code": "ALTER TABLE purchase_returns ADD COLUMN place_of_supply_code VARCHAR NOT NULL DEFAULT ''",
    }
    for col, sql in cols_to_add.items():
        if col not in cols:
            conn.execute(text(sql))


def downgrade():
    conn = op.get_bind()
    for col in ("place_of_supply_code","invoice_type","availed_itc_cess","availed_itc_state_tax",
                "availed_itc_central_tax","availed_itc_integrated_tax","eligibility_for_itc",
                "rate","note_refund_voucher_value","reason_for_issuing_document","pre_gst"):
        conn.execute(text(f"ALTER TABLE purchase_returns DROP COLUMN IF EXISTS {col}"))
