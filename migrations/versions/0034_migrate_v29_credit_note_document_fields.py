"""
v29 — document_type/nature/series on credit_notes.

Ported from app/main.py's _migrate_v29() as part of consolidating the
28 ad-hoc startup ALTER functions into real, ordered Alembic migrations.
The logic below is unchanged from the original function — only the
connection source changed (op.get_bind() instead of a fresh
engine.connect()), so this migration is exactly as idempotent-safe as
the original was, and safe to run against a database that already has
some or all of these columns/tables.

Revision ID: 0034_migrate_v29_credit_note_document_fields
Revises: 0033_migrate_v28_document_fields
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = '0034_migrate_v29_credit_note_document_fields'
down_revision = '0033_migrate_v28_document_fields'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    if "credit_notes" not in inspect(conn).get_table_names():
        return
    cols = {c["name"]: c for c in inspect(conn).get_columns("credit_notes")}
    if "document_type" not in cols:
        conn.execute(text("ALTER TABLE credit_notes ADD COLUMN document_type VARCHAR NULL"))
    if "document_nature" not in cols:
        conn.execute(text("ALTER TABLE credit_notes ADD COLUMN document_nature VARCHAR NULL"))
    if "document_series" not in cols:
        conn.execute(text("ALTER TABLE credit_notes ADD COLUMN document_series VARCHAR NULL"))


def downgrade():
    conn = op.get_bind()
    conn.execute(text("ALTER TABLE credit_notes DROP COLUMN IF EXISTS document_series"))
    conn.execute(text("ALTER TABLE credit_notes DROP COLUMN IF EXISTS document_nature"))
    conn.execute(text("ALTER TABLE credit_notes DROP COLUMN IF EXISTS document_type"))
