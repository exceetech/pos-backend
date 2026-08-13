"""
v31 — GSTR ITC + HSN fields on purchase_items.

Ported from app/main.py's _migrate_v31() as part of consolidating the
28 ad-hoc startup ALTER functions into real, ordered Alembic migrations.
The logic below is unchanged from the original function — only the
connection source changed (op.get_bind() instead of a fresh
engine.connect()), so this migration is exactly as idempotent-safe as
the original was, and safe to run against a database that already has
some or all of these columns/tables.

Revision ID: 0036_migrate_v31_purchase_items_gstr_fields
Revises: 0035_migrate_v30_purchases_gstr_fields
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = '0036_migrate_v31_purchase_items_gstr_fields'
down_revision = '0035_migrate_v30_purchases_gstr_fields'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    if "purchase_items" not in inspect(conn).get_table_names():
        return
    cols = {c["name"]: c for c in inspect(conn).get_columns("purchase_items")}

    cols_to_add = {
        "cess_percentage": "ALTER TABLE purchase_items ADD COLUMN cess_percentage DOUBLE PRECISION NOT NULL DEFAULT 0.0",
        "cess_amount": "ALTER TABLE purchase_items ADD COLUMN cess_amount DOUBLE PRECISION NOT NULL DEFAULT 0.0",
        "eligibility_for_itc": "ALTER TABLE purchase_items ADD COLUMN eligibility_for_itc VARCHAR NOT NULL DEFAULT 'Inputs'",
        "availed_itc_igst": "ALTER TABLE purchase_items ADD COLUMN availed_itc_igst DOUBLE PRECISION NOT NULL DEFAULT 0.0",
        "availed_itc_cgst": "ALTER TABLE purchase_items ADD COLUMN availed_itc_cgst DOUBLE PRECISION NOT NULL DEFAULT 0.0",
        "availed_itc_sgst": "ALTER TABLE purchase_items ADD COLUMN availed_itc_sgst DOUBLE PRECISION NOT NULL DEFAULT 0.0",
        "availed_itc_cess": "ALTER TABLE purchase_items ADD COLUMN availed_itc_cess DOUBLE PRECISION NOT NULL DEFAULT 0.0",
        "hsn_description": "ALTER TABLE purchase_items ADD COLUMN hsn_description VARCHAR NOT NULL DEFAULT ''",
        "official_uqc": "ALTER TABLE purchase_items ADD COLUMN official_uqc VARCHAR NOT NULL DEFAULT ''",
    }
    for col, sql in cols_to_add.items():
        if col not in cols:
            conn.execute(text(sql))


def downgrade():
    conn = op.get_bind()
    for col in ("official_uqc","hsn_description","availed_itc_cess","availed_itc_sgst",
                "availed_itc_cgst","availed_itc_igst","eligibility_for_itc",
                "cess_amount","cess_percentage"):
        conn.execute(text(f"ALTER TABLE purchase_items DROP COLUMN IF EXISTS {col}"))
