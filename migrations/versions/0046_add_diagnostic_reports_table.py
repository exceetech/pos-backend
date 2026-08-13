"""
New table: diagnostic_reports — a one-shot, on-demand full local event-log
dump uploaded silently from a single device (see UserEventLogger /
DiagnosticReportUploader on Android), separate from the always-syncing,
90-day-retention user_event_logs table.

Indexed on shop_id (support pulls a shop's most recent report) and
created_at (the cleanup job — see
app/services/diagnostic_report_cleanup_service.py — filters/deletes by
this). Short retention (14 days) since a report is only useful while a
specific investigation is active.

Idempotent (checks table existence first), safe to re-run.

Revision ID: 0046_add_diagnostic_reports_table
Revises: 0045_add_user_event_logs_table
Create Date: 2026-08-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0046_add_diagnostic_reports_table"
down_revision = "0045_add_user_event_logs_table"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    existing_tables = set(inspect(conn).get_table_names())
    if "diagnostic_reports" in existing_tables:
        return

    op.create_table(
        "diagnostic_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shop_id", sa.Integer(), sa.ForeignKey("shops.id"), nullable=False),
        sa.Column("events", sa.JSON(), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_diagnostic_reports_shop_id", "diagnostic_reports", ["shop_id"])
    op.create_index("ix_diagnostic_reports_created_at", "diagnostic_reports", ["created_at"])


def downgrade():
    conn = op.get_bind()
    existing_tables = set(inspect(conn).get_table_names())
    if "diagnostic_reports" not in existing_tables:
        return
    op.drop_index("ix_diagnostic_reports_created_at", table_name="diagnostic_reports")
    op.drop_index("ix_diagnostic_reports_shop_id", table_name="diagnostic_reports")
    op.drop_table("diagnostic_reports")
