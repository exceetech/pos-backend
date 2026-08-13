"""
sale_items.bill_number + its lookup index.

Ported from app/main.py's _add_sale_items_bill_number() as part of consolidating the
28 ad-hoc startup ALTER functions into real, ordered Alembic migrations.
The logic below is unchanged from the original function — only the
connection source changed (op.get_bind() instead of a fresh
engine.connect()), so this migration is exactly as idempotent-safe as
the original was, and safe to run against a database that already has
some or all of these columns/tables.

Revision ID: 0025_add_sale_items_bill_number
Revises: 0024_add_global_variant_autofill
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = '0025_add_sale_items_bill_number'
down_revision = '0024_add_global_variant_autofill'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    table = "sale_items"
    inspector = inspect(conn)
    if table not in set(inspector.get_table_names()):
        return

    existing = {c["name"] for c in inspector.get_columns(table)}
    if "bill_number" not in existing:
        conn.execute(text("ALTER TABLE sale_items ADD COLUMN bill_number VARCHAR NULL"))

    index_names = {ix["name"] for ix in inspect(conn).get_indexes(table)}
    if "ix_sale_items_bill_number" not in index_names:
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_sale_items_bill_number "
            "ON sale_items (bill_number)"
        ))


def downgrade():
    conn = op.get_bind()
    conn.execute(text("DROP INDEX IF EXISTS ix_sale_items_bill_number"))
    conn.execute(text("ALTER TABLE sale_items DROP COLUMN IF EXISTS bill_number"))
