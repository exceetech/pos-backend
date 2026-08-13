"""
v25 — Debit Note columns on purchase_returns + credit_notes /
credit_note_items tables.

Ported from app/main.py's _migrate_v25() as part of consolidating the
28 ad-hoc startup ALTER functions into real, ordered Alembic migrations.
The logic below is unchanged from the original function — only the
connection source changed (op.get_bind() instead of a fresh
engine.connect()), so this migration is exactly as idempotent-safe as
the original was, and safe to run against a database that already has
some or all of these columns/tables.

Revision ID: 0031_migrate_v25_credit_notes
Revises: 0030_migrate_customer_unique_key
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = '0031_migrate_v25_credit_notes'
down_revision = '0030_migrate_customer_unique_key'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    from app.models.credit_note import CreditNote, CreditNoteItem  # noqa: F401
    CreditNote.__table__.create(bind=conn, checkfirst=True)
    CreditNoteItem.__table__.create(bind=conn, checkfirst=True)

    new_cols = [
        ("note_number",             "note_number VARCHAR NULL"),
        ("note_date",               "note_date BIGINT NULL"),
        ("note_type",               "note_type VARCHAR(1) NULL"),
        ("original_invoice_id",     "original_invoice_id INTEGER NULL"),
        ("original_invoice_number", "original_invoice_number VARCHAR NULL"),
        ("original_invoice_date",   "original_invoice_date BIGINT NULL"),
        ("place_of_supply",         "place_of_supply VARCHAR NULL"),
        ("supply_type",             "supply_type VARCHAR NULL DEFAULT 'intrastate'"),
        ("cess_amount",             "cess_amount DOUBLE PRECISION NULL DEFAULT 0.0"),
    ]
    nullable_cols = {
        "note_number", "note_date", "note_type",
        "original_invoice_id", "original_invoice_number", "original_invoice_date",
        "place_of_supply", "supply_type", "cess_amount",
    }

    inspector = inspect(conn)
    existing_col_info = {c["name"]: c for c in inspector.get_columns("purchase_returns")}
    existing = set(existing_col_info.keys())

    for col_name, ddl in new_cols:
        if col_name not in existing:
            conn.execute(text(f"ALTER TABLE purchase_returns ADD COLUMN {ddl}"))
            existing.add(col_name)
        elif col_name in nullable_cols:
            try:
                conn.execute(text(
                    f"ALTER TABLE purchase_returns "
                    f"ALTER COLUMN {col_name} DROP NOT NULL"
                ))
            except Exception:
                pass


def downgrade():
    # Not reversed: credit_notes/credit_note_items may hold real documents
    # by the time this would ever be downgraded, and the purchase_returns
    # columns are shared with later migrations (v27/v29/v32/v33). Restore
    # from backup if this must be undone.
    pass
