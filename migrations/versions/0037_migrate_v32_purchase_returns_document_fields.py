"""
v32 — document_type/nature/series on purchase_returns.

Ported from app/main.py's _migrate_v32() as part of consolidating the
28 ad-hoc startup ALTER functions into real, ordered Alembic migrations.
The logic below is unchanged from the original function — only the
connection source changed (op.get_bind() instead of a fresh
engine.connect()), so this migration is exactly as idempotent-safe as
the original was, and safe to run against a database that already has
some or all of these columns/tables.

Revision ID: 0037_migrate_v32_purchase_returns_document_fields
Revises: 0036_migrate_v31_purchase_items_gstr_fields
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = '0037_migrate_v32_purchase_returns_document_fields'
down_revision = '0036_migrate_v31_purchase_items_gstr_fields'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    if "purchase_returns" not in inspect(conn).get_table_names():
        return
    cols = {c["name"]: c for c in inspect(conn).get_columns("purchase_returns")}

    cols_to_add = {
        "document_type": "ALTER TABLE purchase_returns ADD COLUMN document_type VARCHAR NULL",
        "document_nature": "ALTER TABLE purchase_returns ADD COLUMN document_nature VARCHAR NULL",
        "document_series": "ALTER TABLE purchase_returns ADD COLUMN document_series VARCHAR NULL",
    }
    for col, sql in cols_to_add.items():
        if col not in cols:
            conn.execute(text(sql))


def downgrade():
    conn = op.get_bind()
    for col in ("document_series","document_nature","document_type"):
        conn.execute(text(f"ALTER TABLE purchase_returns DROP COLUMN IF EXISTS {col}"))
