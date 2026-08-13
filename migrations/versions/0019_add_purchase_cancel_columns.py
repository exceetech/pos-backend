"""
purchases.is_cancelled / cancelled_at (void support).

Ported from app/main.py's _add_purchase_cancel_columns() as part of consolidating the
28 ad-hoc startup ALTER functions into real, ordered Alembic migrations.
The logic below is unchanged from the original function — only the
connection source changed (op.get_bind() instead of a fresh
engine.connect()), so this migration is exactly as idempotent-safe as
the original was, and safe to run against a database that already has
some or all of these columns/tables.

Revision ID: 0019_add_purchase_cancel_columns
Revises: 0018_add_credit_columns_to_purchases
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = '0019_add_purchase_cancel_columns'
down_revision = '0018_add_credit_columns_to_purchases'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    cols_to_add = {
        "is_cancelled": "ALTER TABLE purchases ADD COLUMN is_cancelled INTEGER NOT NULL DEFAULT 0",
        "cancelled_at": "ALTER TABLE purchases ADD COLUMN cancelled_at TIMESTAMP NULL",
    }
    existing = {c["name"] for c in inspect(conn).get_columns("purchases")}
    for col, sql in cols_to_add.items():
        if col not in existing:
            conn.execute(text(sql))


def downgrade():
    conn = op.get_bind()
    conn.execute(text("ALTER TABLE purchases DROP COLUMN IF EXISTS cancelled_at"))
    conn.execute(text("ALTER TABLE purchases DROP COLUMN IF EXISTS is_cancelled"))
