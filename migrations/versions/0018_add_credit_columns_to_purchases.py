"""
purchases.is_credit / credit_account_id.

Ported from app/main.py's _add_credit_columns_to_purchases() as part of consolidating the
28 ad-hoc startup ALTER functions into real, ordered Alembic migrations.
The logic below is unchanged from the original function — only the
connection source changed (op.get_bind() instead of a fresh
engine.connect()), so this migration is exactly as idempotent-safe as
the original was, and safe to run against a database that already has
some or all of these columns/tables.

Revision ID: 0018_add_credit_columns_to_purchases
Revises: 0017_add_invoice_date_column
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = '0018_add_credit_columns_to_purchases'
down_revision = '0017_add_invoice_date_column'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    cols_to_add = {
        "is_credit":         "ALTER TABLE purchases ADD COLUMN is_credit INTEGER NOT NULL DEFAULT 0",
        "credit_account_id": "ALTER TABLE purchases ADD COLUMN credit_account_id INTEGER NULL",
    }
    existing = {c["name"] for c in inspect(conn).get_columns("purchases")}
    for col, sql in cols_to_add.items():
        if col not in existing:
            conn.execute(text(sql))


def downgrade():
    conn = op.get_bind()
    conn.execute(text("ALTER TABLE purchases DROP COLUMN IF EXISTS credit_account_id"))
    conn.execute(text("ALTER TABLE purchases DROP COLUMN IF EXISTS is_credit"))
