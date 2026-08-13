"""
v41 — Move customers unique key from (shop_id, phone) to
(shop_id, phone, customer_type) so B2C/B2B can share a phone number.

Ported from app/main.py's _migrate_customer_unique_key() as part of consolidating the
28 ad-hoc startup ALTER functions into real, ordered Alembic migrations.
The logic below is unchanged from the original function — only the
connection source changed (op.get_bind() instead of a fresh
engine.connect()), so this migration is exactly as idempotent-safe as
the original was, and safe to run against a database that already has
some or all of these columns/tables.

Revision ID: 0030_migrate_customer_unique_key
Revises: 0029_ensure_supplier_table
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = '0030_migrate_customer_unique_key'
down_revision = '0029_ensure_supplier_table'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    if "customers" not in inspect(conn).get_table_names():
        return
    for stmt in (
        "ALTER TABLE customers DROP CONSTRAINT IF EXISTS uix_customer_shop_phone",
        "DROP INDEX IF EXISTS uix_customer_shop_phone",
    ):
        try:
            conn.execute(text(stmt))
        except Exception:
            pass
    try:
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uix_customer_shop_phone_type "
            "ON customers (shop_id, phone, customer_type)"
        ))
    except Exception:
        pass


def downgrade():
    conn = op.get_bind()
    conn.execute(text("DROP INDEX IF EXISTS uix_customer_shop_phone_type"))
    # The original 2-column constraint is not restored automatically —
    # recreating it could fail if any shop now has duplicate (shop_id, phone)
    # rows across customer_type, which is exactly what this migration made
    # legal. Restore from backup if the old constraint must come back.
