"""
Adds customer-facing UPI QR code fields to bills — the scan-to-pay
in-person alternative to the existing Payment Link fields (0052).

razorpay_qr_id is what the "qr_code.credited" webhook is matched back
against, since QR codes don't carry a reference_id the way Payment
Links do.

Idempotent (checks column existence first), safe to re-run.

Revision ID: 0054_add_bill_qr_fields
Revises: 0053_add_shop_razorpay_credentials
Create Date: 2026-08-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0054_add_bill_qr_fields"
down_revision = "0053_add_shop_razorpay_credentials"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    columns = {c["name"] for c in inspect(conn).get_columns("bills")}

    if "razorpay_qr_id" not in columns:
        op.add_column("bills", sa.Column("razorpay_qr_id", sa.String(), nullable=True))
        op.create_index("ix_bills_razorpay_qr_id", "bills", ["razorpay_qr_id"])
    if "razorpay_qr_image_url" not in columns:
        op.add_column("bills", sa.Column("razorpay_qr_image_url", sa.String(), nullable=True))


def downgrade():
    conn = op.get_bind()
    columns = {c["name"] for c in inspect(conn).get_columns("bills")}

    if "razorpay_qr_image_url" in columns:
        op.drop_column("bills", "razorpay_qr_image_url")
    if "razorpay_qr_id" in columns:
        op.drop_index("ix_bills_razorpay_qr_id", table_name="bills")
        op.drop_column("bills", "razorpay_qr_id")
