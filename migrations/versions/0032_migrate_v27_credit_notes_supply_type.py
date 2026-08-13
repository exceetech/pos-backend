"""
v27 — credit_notes.note_supply_type.

Ported from app/main.py's _migrate_v27() as part of consolidating the
28 ad-hoc startup ALTER functions into real, ordered Alembic migrations.
The logic below is unchanged from the original function — only the
connection source changed (op.get_bind() instead of a fresh
engine.connect()), so this migration is exactly as idempotent-safe as
the original was, and safe to run against a database that already has
some or all of these columns/tables.

Revision ID: 0032_migrate_v27_credit_notes_supply_type
Revises: 0031_migrate_v25_credit_notes
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = '0032_migrate_v27_credit_notes_supply_type'
down_revision = '0031_migrate_v25_credit_notes'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    if "credit_notes" not in inspect(conn).get_table_names():
        return
    cols = {c["name"]: c for c in inspect(conn).get_columns("credit_notes")}
    if "note_supply_type" not in cols:
        conn.execute(text("ALTER TABLE credit_notes ADD COLUMN note_supply_type VARCHAR NULL DEFAULT 'Regular'"))


def downgrade():
    conn = op.get_bind()
    conn.execute(text("ALTER TABLE credit_notes DROP COLUMN IF EXISTS note_supply_type"))
