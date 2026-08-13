"""
One-time data cleanup: deactivate pre-existing bill rows that have
no created_at (predate that column) so they stop polluting reports.

Ported from app/main.py's _deactivate_stale_bills() as part of consolidating the
28 ad-hoc startup ALTER functions into real, ordered Alembic migrations.
The logic below is unchanged from the original function — only the
connection source changed (op.get_bind() instead of a fresh
engine.connect()), so this migration is exactly as idempotent-safe as
the original was, and safe to run against a database that already has
some or all of these columns/tables.

Revision ID: 0040_deactivate_stale_bills
Revises: 0039_migrate_v34_purchase_import_details
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = '0040_deactivate_stale_bills'
down_revision = '0039_migrate_v34_purchase_import_details'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    r1 = conn.execute(text(
        "UPDATE bills SET active = FALSE "
        "WHERE created_at IS NULL AND active = TRUE"
    ))
    if r1.rowcount:
        print(f"[migration 0040] deactivated {r1.rowcount} stale bill(s) with NULL created_at")


def downgrade():
    # Deliberately not reversed: this was a one-time data correction, not a
    # schema change, and re-activating those bills would resurface data
    # that was intentionally excluded from reports as unreliable/pre-dated.
    pass
