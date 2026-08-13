"""
Retire the legacy gst_sales_records table — fully superseded by
gst_sales_invoice(+items); nothing reads or writes it anymore.

Ported from app/main.py's _drop_legacy_gst_sales_records_table() as part of consolidating the
28 ad-hoc startup ALTER functions into real, ordered Alembic migrations.
The logic below is unchanged from the original function — only the
connection source changed (op.get_bind() instead of a fresh
engine.connect()), so this migration is exactly as idempotent-safe as
the original was, and safe to run against a database that already has
some or all of these columns/tables.

Revision ID: 0023_drop_legacy_gst_sales_records_table
Revises: 0022_add_gstr_support_columns
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = '0023_drop_legacy_gst_sales_records_table'
down_revision = '0022_add_gstr_support_columns'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(text("DROP TABLE IF EXISTS gst_sales_records"))


def downgrade():
    # Deliberately irreversible: the table (and any pre-cutover rows in it)
    # was intentionally retired; recreating an empty shell here would be
    # misleading. Restore from a pre-upgrade backup if the data is needed.
    pass
