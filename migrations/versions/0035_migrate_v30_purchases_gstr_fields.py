"""
v30 — local_id + GSTR ITC fields on purchases, plus local_id index.

Ported from app/main.py's _migrate_v30() as part of consolidating the
28 ad-hoc startup ALTER functions into real, ordered Alembic migrations.
The logic below is unchanged from the original function — only the
connection source changed (op.get_bind() instead of a fresh
engine.connect()), so this migration is exactly as idempotent-safe as
the original was, and safe to run against a database that already has
some or all of these columns/tables.

Revision ID: 0035_migrate_v30_purchases_gstr_fields
Revises: 0034_migrate_v29_credit_note_document_fields
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = '0035_migrate_v30_purchases_gstr_fields'
down_revision = '0034_migrate_v29_credit_note_document_fields'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    if "purchases" not in inspect(conn).get_table_names():
        return
    cols = {c["name"]: c for c in inspect(conn).get_columns("purchases")}

    cols_to_add = {
        "local_id": "ALTER TABLE purchases ADD COLUMN local_id INTEGER NULL",
        "place_of_supply_code": "ALTER TABLE purchases ADD COLUMN place_of_supply_code VARCHAR NOT NULL DEFAULT ''",
        "reverse_charge": "ALTER TABLE purchases ADD COLUMN reverse_charge VARCHAR NOT NULL DEFAULT 'N'",
        "invoice_type": "ALTER TABLE purchases ADD COLUMN invoice_type VARCHAR NOT NULL DEFAULT 'Regular'",
        "supply_type": "ALTER TABLE purchases ADD COLUMN supply_type VARCHAR NOT NULL DEFAULT 'intrastate'",
        "cess_paid": "ALTER TABLE purchases ADD COLUMN cess_paid DOUBLE PRECISION NOT NULL DEFAULT 0.0",
        "eligibility_for_itc": "ALTER TABLE purchases ADD COLUMN eligibility_for_itc VARCHAR NOT NULL DEFAULT 'Inputs'",
        "availed_itc_integrated_tax": "ALTER TABLE purchases ADD COLUMN availed_itc_integrated_tax DOUBLE PRECISION NOT NULL DEFAULT 0.0",
        "availed_itc_central_tax": "ALTER TABLE purchases ADD COLUMN availed_itc_central_tax DOUBLE PRECISION NOT NULL DEFAULT 0.0",
        "availed_itc_state_tax": "ALTER TABLE purchases ADD COLUMN availed_itc_state_tax DOUBLE PRECISION NOT NULL DEFAULT 0.0",
        "availed_itc_cess": "ALTER TABLE purchases ADD COLUMN availed_itc_cess DOUBLE PRECISION NOT NULL DEFAULT 0.0",
    }
    for col, sql in cols_to_add.items():
        if col not in cols:
            conn.execute(text(sql))

    try:
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_purchases_local_id ON purchases (local_id)"))
    except Exception:
        pass


def downgrade():
    conn = op.get_bind()
    conn.execute(text("DROP INDEX IF EXISTS ix_purchases_local_id"))
    for col in ("availed_itc_cess","availed_itc_state_tax","availed_itc_central_tax",
                "availed_itc_integrated_tax","eligibility_for_itc","cess_paid",
                "supply_type","invoice_type","reverse_charge","place_of_supply_code","local_id"):
        conn.execute(text(f"ALTER TABLE purchases DROP COLUMN IF EXISTS {col}"))
