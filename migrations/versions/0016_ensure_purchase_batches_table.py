"""
Hybrid-inventory: ensure purchase_batches exists on deployed DBs.

Ported from app/main.py's _ensure_purchase_batches_table() as part of consolidating the
28 ad-hoc startup ALTER functions into real, ordered Alembic migrations.
The logic below is unchanged from the original function — only the
connection source changed (op.get_bind() instead of a fresh
engine.connect()), so this migration is exactly as idempotent-safe as
the original was, and safe to run against a database that already has
some or all of these columns/tables.

Revision ID: 0016_ensure_purchase_batches_table
Revises: 0015_ensure_bills_table
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = '0016_ensure_purchase_batches_table'
down_revision = '0015_ensure_bills_table'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = inspect(conn)
    if "purchase_batches" not in insp.get_table_names():
        from app.models.purchase_batch import PurchaseBatch
        PurchaseBatch.__table__.create(bind=conn, checkfirst=True)


def downgrade():
    op.execute(text("DROP TABLE IF EXISTS purchase_batches"))
