"""
Moving-average redesign, phase 2 —
purchase_returns.inventory_valuation_variance.

Ported from app/main.py's _add_purchase_return_variance_column() as part of consolidating the
28 ad-hoc startup ALTER functions into real, ordered Alembic migrations.
The logic below is unchanged from the original function — only the
connection source changed (op.get_bind() instead of a fresh
engine.connect()), so this migration is exactly as idempotent-safe as
the original was, and safe to run against a database that already has
some or all of these columns/tables.

Revision ID: 0042_add_purchase_return_variance_column
Revises: 0041_add_inventory_log_resulting_avg_cost_column
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = '0042_add_purchase_return_variance_column'
down_revision = '0041_add_inventory_log_resulting_avg_cost_column'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    if "purchase_returns" not in inspect(conn).get_table_names():
        return
    cols = {c["name"] for c in inspect(conn).get_columns("purchase_returns")}
    if "inventory_valuation_variance" not in cols:
        conn.execute(text(
            "ALTER TABLE purchase_returns ADD COLUMN inventory_valuation_variance DOUBLE PRECISION NOT NULL DEFAULT 0.0"
        ))


def downgrade():
    conn = op.get_bind()
    conn.execute(text("ALTER TABLE purchase_returns DROP COLUMN IF EXISTS inventory_valuation_variance"))
