"""
Payment & cash-flow tracking - the Money Book table `money_entries`.

Additive and idempotent (creates the table only if missing).

Revision ID: 0060_add_money_entries
Revises: 0059_sale_allocation_origin
Create Date: 2026-10-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0060_add_money_entries"
down_revision = "0059_sale_allocation_origin"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    if "money_entries" in set(inspect(conn).get_table_names()):
        return
    op.create_table(
        "money_entries",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("shop_id", sa.Integer, sa.ForeignKey("shops.id"), nullable=False),
        sa.Column("uid", sa.String(40), nullable=False),
        sa.Column("origin", sa.String(40), nullable=False, server_default=""),
        sa.Column("local_id", sa.Integer, nullable=False, server_default="0"),
        sa.Column("direction", sa.String(3), nullable=False),
        sa.Column("mode", sa.String(8), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("reason", sa.String(24), nullable=False),
        sa.Column("source_type", sa.String(24), nullable=False),
        sa.Column("source_id", sa.Integer, nullable=False, server_default="0"),
        sa.Column("parent_type", sa.String(24), nullable=False),
        sa.Column("parent_id", sa.Integer, nullable=False, server_default="0"),
        sa.Column("party_name", sa.String(120), nullable=False, server_default=""),
        sa.Column("ref_text", sa.String(60), nullable=False, server_default=""),
        sa.Column("status", sa.String(10), nullable=False, server_default="RECEIVED"),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("shop_id", "uid", name="uq_money_entry_shop_uid"),
    )
    op.create_index("ix_money_entries_id", "money_entries", ["id"])
    op.create_index("ix_money_entries_shop_id", "money_entries", ["shop_id"])
    op.create_index("ix_money_entries_shop_created", "money_entries", ["shop_id", "created_at"])


def downgrade():
    op.drop_table("money_entries")
