"""
Suppliers master table.

Ported from app/main.py's _ensure_supplier_table() as part of consolidating the
28 ad-hoc startup ALTER functions into real, ordered Alembic migrations.
The logic below is unchanged from the original function — only the
connection source changed (op.get_bind() instead of a fresh
engine.connect()), so this migration is exactly as idempotent-safe as
the original was, and safe to run against a database that already has
some or all of these columns/tables.

Revision ID: 0029_ensure_supplier_table
Revises: 0028_ensure_v40_tables
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = '0029_ensure_supplier_table'
down_revision = '0028_ensure_v40_tables'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    from app.models.supplier import Supplier
    Supplier.__table__.create(bind=conn, checkfirst=True)


def downgrade():
    op.execute(text("DROP TABLE IF EXISTS suppliers"))
