"""
Moving-average redesign — inventory_log.resulting_average_cost.

Ported from app/main.py's _add_inventory_log_resulting_avg_cost_column() as part of consolidating the
28 ad-hoc startup ALTER functions into real, ordered Alembic migrations.
The logic below is unchanged from the original function — only the
connection source changed (op.get_bind() instead of a fresh
engine.connect()), so this migration is exactly as idempotent-safe as
the original was, and safe to run against a database that already has
some or all of these columns/tables.

Revision ID: 0041_add_inventory_log_resulting_avg_cost_column
Revises: 0040_deactivate_stale_bills
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = '0041_add_inventory_log_resulting_avg_cost_column'
down_revision = '0040_deactivate_stale_bills'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    if "inventory_log" not in inspect(conn).get_table_names():
        return
    cols = {c["name"] for c in inspect(conn).get_columns("inventory_log")}
    if "resulting_average_cost" not in cols:
        conn.execute(text(
            "ALTER TABLE inventory_log ADD COLUMN resulting_average_cost DOUBLE PRECISION NOT NULL DEFAULT 0.0"
        ))


def downgrade():
    conn = op.get_bind()
    conn.execute(text("ALTER TABLE inventory_log DROP COLUMN IF EXISTS resulting_average_cost"))
