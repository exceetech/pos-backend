"""
Belt-and-braces: ensure bills and bill_items exist (create_all()
normally handles this; this is a defensive backstop).

Ported from app/main.py's _ensure_bills_table() as part of consolidating the
28 ad-hoc startup ALTER functions into real, ordered Alembic migrations.
The logic below is unchanged from the original function — only the
connection source changed (op.get_bind() instead of a fresh
engine.connect()), so this migration is exactly as idempotent-safe as
the original was, and safe to run against a database that already has
some or all of these columns/tables.

Revision ID: 0015_ensure_bills_table
Revises: 0014_subscription_entitlement
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = '0015_ensure_bills_table'
down_revision = '0014_subscription_entitlement'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    from app.models.bill import Bill
    from app.models.bill_items import BillItem
    Bill.__table__.create(bind=conn, checkfirst=True)
    BillItem.__table__.create(bind=conn, checkfirst=True)


def downgrade():
    # No-op: these are core tables created by the very first migrations /
    # create_all(); this migration never owned their lifecycle, only
    # defensively ensured they exist.
    pass
