"""
purchases.invoice_date — idempotent ALTER for already-deployed DBs.

Ported from app/main.py's _add_invoice_date_column() as part of consolidating the
28 ad-hoc startup ALTER functions into real, ordered Alembic migrations.
The logic below is unchanged from the original function — only the
connection source changed (op.get_bind() instead of a fresh
engine.connect()), so this migration is exactly as idempotent-safe as
the original was, and safe to run against a database that already has
some or all of these columns/tables.

Revision ID: 0017_add_invoice_date_column
Revises: 0016_ensure_purchase_batches_table
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = '0017_add_invoice_date_column'
down_revision = '0016_ensure_purchase_batches_table'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    cols = {c["name"] for c in inspect(conn).get_columns("purchases")}
    if "invoice_date" not in cols:
        conn.execute(text("ALTER TABLE purchases ADD COLUMN invoice_date TIMESTAMP NULL"))


def downgrade():
    conn = op.get_bind()
    conn.execute(text("ALTER TABLE purchases DROP COLUMN IF EXISTS invoice_date"))
