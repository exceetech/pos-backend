"""
Server-set updated_at cursors for delta pulls (Sync audit S5),
with backfill so a first delta pull still returns pre-existing rows.

Ported from app/main.py's _add_delta_cursor_columns() as part of consolidating the
28 ad-hoc startup ALTER functions into real, ordered Alembic migrations.
The logic below is unchanged from the original function — only the
connection source changed (op.get_bind() instead of a fresh
engine.connect()), so this migration is exactly as idempotent-safe as
the original was, and safe to run against a database that already has
some or all of these columns/tables.

Revision ID: 0021_add_delta_cursor_columns
Revises: 0020_add_sync_idempotency_columns
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = '0021_add_delta_cursor_columns'
down_revision = '0020_add_sync_idempotency_columns'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    specs = [
        ("inventory", "updated_at",
         "ALTER TABLE inventory ADD COLUMN updated_at TIMESTAMP NULL",
         "UPDATE inventory SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL"),
        ("purchases", "updated_at",
         "ALTER TABLE purchases ADD COLUMN updated_at TIMESTAMP NULL",
         "UPDATE purchases SET updated_at = COALESCE(created_at, CURRENT_TIMESTAMP) "
         "WHERE updated_at IS NULL"),
        ("bills", "updated_at",
         "ALTER TABLE bills ADD COLUMN updated_at TIMESTAMP NULL",
         "UPDATE bills SET updated_at = COALESCE(created_at, CURRENT_TIMESTAMP) "
         "WHERE updated_at IS NULL"),
    ]
    inspector = inspect(conn)
    for table, col, add_sql, backfill_sql in specs:
        existing = {c["name"] for c in inspector.get_columns(table)}
        if col not in existing:
            conn.execute(text(add_sql))
            conn.execute(text(backfill_sql))


def downgrade():
    conn = op.get_bind()
    conn.execute(text("ALTER TABLE bills DROP COLUMN IF EXISTS updated_at"))
    conn.execute(text("ALTER TABLE purchases DROP COLUMN IF EXISTS updated_at"))
    conn.execute(text("ALTER TABLE inventory DROP COLUMN IF EXISTS updated_at"))
