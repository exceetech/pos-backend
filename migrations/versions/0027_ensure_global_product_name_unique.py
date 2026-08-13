"""
Unique index on global_products.name for already-deployed DBs.

Ported from app/main.py's _ensure_global_product_name_unique() as part of consolidating the
28 ad-hoc startup ALTER functions into real, ordered Alembic migrations.
The logic below is unchanged from the original function — only the
connection source changed (op.get_bind() instead of a fresh
engine.connect()), so this migration is exactly as idempotent-safe as
the original was, and safe to run against a database that already has
some or all of these columns/tables.

Revision ID: 0027_ensure_global_product_name_unique
Revises: 0026_add_sale_items_idempotency_cols
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = '0027_ensure_global_product_name_unique'
down_revision = '0026_add_sale_items_idempotency_cols'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    if "global_products" not in set(inspect(conn).get_table_names()):
        return

    inspector = inspect(conn)
    has_unique = (
        any("name" in uc.get("column_names", [])
            for uc in inspector.get_unique_constraints("global_products"))
        or any(ix.get("unique") and ix.get("column_names") == ["name"]
               for ix in inspector.get_indexes("global_products"))
    )
    if has_unique:
        return

    conn.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uix_global_products_name "
        "ON global_products (name)"
    ))


def downgrade():
    conn = op.get_bind()
    conn.execute(text("DROP INDEX IF EXISTS uix_global_products_name"))
