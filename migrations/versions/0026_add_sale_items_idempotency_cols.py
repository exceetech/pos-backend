"""
sale_items.client_bill_id / client_device_id (Report 5 fix) + index.

Ported from app/main.py's _add_sale_items_idempotency_cols() as part of consolidating the
28 ad-hoc startup ALTER functions into real, ordered Alembic migrations.
The logic below is unchanged from the original function — only the
connection source changed (op.get_bind() instead of a fresh
engine.connect()), so this migration is exactly as idempotent-safe as
the original was, and safe to run against a database that already has
some or all of these columns/tables.

Revision ID: 0026_add_sale_items_idempotency_cols
Revises: 0025_add_sale_items_bill_number
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = '0026_add_sale_items_idempotency_cols'
down_revision = '0025_add_sale_items_bill_number'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    table = "sale_items"
    inspector = inspect(conn)
    if table not in set(inspector.get_table_names()):
        return

    existing = {c["name"] for c in inspector.get_columns(table)}
    if "client_bill_id" not in existing:
        conn.execute(text("ALTER TABLE sale_items ADD COLUMN client_bill_id INTEGER NULL"))
    if "client_device_id" not in existing:
        conn.execute(text("ALTER TABLE sale_items ADD COLUMN client_device_id VARCHAR NULL"))

    index_names = {ix["name"] for ix in inspect(conn).get_indexes(table)}
    if "ix_sale_items_client_bill_id" not in index_names:
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_sale_items_client_bill_id "
            "ON sale_items (client_bill_id)"
        ))


def downgrade():
    conn = op.get_bind()
    conn.execute(text("DROP INDEX IF EXISTS ix_sale_items_client_bill_id"))
    conn.execute(text("ALTER TABLE sale_items DROP COLUMN IF EXISTS client_device_id"))
    conn.execute(text("ALTER TABLE sale_items DROP COLUMN IF EXISTS client_bill_id"))
