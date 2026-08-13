"""
New table: user_event_logs — a per-shop breadcrumb trail (screens opened,
actions tapped, validation failures, sync/exception errors) so that when a
shop reports a bug, support can pull up their recent events and tell
whether it was a real app bug or an expected validation error / user
mistake.

Indexed on shop_id (every support lookup filters by shop) and created_at
(the daily 90-day cleanup job — see app/services/event_log_cleanup_service.py
— filters/deletes by this).

Idempotent (checks table existence first), safe to re-run.

Revision ID: 0045_add_user_event_logs_table
Revises: 0044_add_missing_fk_indexes
Create Date: 2026-08-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0045_add_user_event_logs_table"
down_revision = "0044_add_missing_fk_indexes"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    existing_tables = set(inspect(conn).get_table_names())
    if "user_event_logs" in existing_tables:
        return

    op.create_table(
        "user_event_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shop_id", sa.Integer(), sa.ForeignKey("shops.id"), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("screen", sa.String(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_user_event_logs_shop_id", "user_event_logs", ["shop_id"])
    op.create_index("ix_user_event_logs_created_at", "user_event_logs", ["created_at"])


def downgrade():
    conn = op.get_bind()
    existing_tables = set(inspect(conn).get_table_names())
    if "user_event_logs" not in existing_tables:
        return
    op.drop_index("ix_user_event_logs_created_at", table_name="user_event_logs")
    op.drop_index("ix_user_event_logs_shop_id", table_name="user_event_logs")
    op.drop_table("user_event_logs")
