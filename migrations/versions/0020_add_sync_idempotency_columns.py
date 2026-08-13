"""
Idempotency keys for offline-replay dedupe (Sync audit S2):
purchase_returns.local_id, inventory_logs.client_uid, scrap_entries.local_id.

Ported from app/main.py's _add_sync_idempotency_columns() as part of consolidating the
28 ad-hoc startup ALTER functions into real, ordered Alembic migrations.
The logic below is unchanged from the original function — only the
connection source changed (op.get_bind() instead of a fresh
engine.connect()), so this migration is exactly as idempotent-safe as
the original was, and safe to run against a database that already has
some or all of these columns/tables.

Revision ID: 0020_add_sync_idempotency_columns
Revises: 0019_add_purchase_cancel_columns
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = '0020_add_sync_idempotency_columns'
down_revision = '0019_add_purchase_cancel_columns'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    targets = {
        "purchase_returns": ("local_id",
            "ALTER TABLE purchase_returns ADD COLUMN local_id INTEGER NULL"),
        "inventory_logs": ("client_uid",
            "ALTER TABLE inventory_logs ADD COLUMN client_uid VARCHAR NULL"),
        "scrap_entries": ("local_id",
            "ALTER TABLE scrap_entries ADD COLUMN local_id INTEGER NULL"),
    }
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())
    for table, (col, sql) in targets.items():
        if table not in existing_tables:
            continue
        existing = {c["name"] for c in inspector.get_columns(table)}
        if col not in existing:
            conn.execute(text(sql))
    if "scrap_entries" in existing_tables:
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_scrap_entries_shop_local "
            "ON scrap_entries (shop_id, local_id)"
        ))


def downgrade():
    conn = op.get_bind()
    conn.execute(text("DROP INDEX IF EXISTS ix_scrap_entries_shop_local"))
    conn.execute(text("ALTER TABLE scrap_entries DROP COLUMN IF EXISTS local_id"))
    conn.execute(text("ALTER TABLE inventory_logs DROP COLUMN IF EXISTS client_uid"))
    conn.execute(text("ALTER TABLE purchase_returns DROP COLUMN IF EXISTS local_id"))
