"""
Adds customer-facing UPI payment-link fields to bills.

payment_status is independent of the existing payment_method column —
payment_method records how the sale was recorded at checkout (Cash/Card/
UPI/Credit); payment_status tracks whether a separate "send to customer"
Razorpay Payment Link has actually been paid. Every bill defaults to
"unpaid", including ones that never get a link sent at all.

Idempotent (checks column existence first), safe to re-run.

Revision ID: 0052_add_bill_payment_link_fields
Revises: 0051_add_is_raw_material
Create Date: 2026-08-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0052_add_bill_payment_link_fields"
down_revision = "0051_add_is_raw_material"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    columns = {c["name"] for c in inspect(conn).get_columns("bills")}

    if "payment_status" not in columns:
        op.add_column(
            "bills",
            sa.Column("payment_status", sa.String(), nullable=False, server_default="unpaid"),
        )
    if "razorpay_payment_link_id" not in columns:
        op.add_column("bills", sa.Column("razorpay_payment_link_id", sa.String(), nullable=True))
        op.create_index(
            "ix_bills_razorpay_payment_link_id", "bills", ["razorpay_payment_link_id"]
        )
    if "razorpay_payment_link_url" not in columns:
        op.add_column("bills", sa.Column("razorpay_payment_link_url", sa.String(), nullable=True))
    if "razorpay_payment_id" not in columns:
        op.add_column("bills", sa.Column("razorpay_payment_id", sa.String(), nullable=True))


def downgrade():
    conn = op.get_bind()
    columns = {c["name"] for c in inspect(conn).get_columns("bills")}

    if "razorpay_payment_id" in columns:
        op.drop_column("bills", "razorpay_payment_id")
    if "razorpay_payment_link_url" in columns:
        op.drop_column("bills", "razorpay_payment_link_url")
    if "razorpay_payment_link_id" in columns:
        op.drop_index("ix_bills_razorpay_payment_link_id", table_name="bills")
        op.drop_column("bills", "razorpay_payment_link_id")
    if "payment_status" in columns:
        op.drop_column("bills", "payment_status")
