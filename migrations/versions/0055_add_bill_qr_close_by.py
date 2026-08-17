"""
Adds razorpay_qr_close_by (epoch seconds) to bills — lets create-qr in
pos_payment_routes.py know whether a saved razorpay_qr_id is still live
on Razorpay's side before reusing it. Without this, a QR reused after
its own 20-minute close_by has passed would silently hand back a dead
code that can never be scanned/paid again.

Idempotent (checks column existence first), safe to re-run.

Revision ID: 0055_add_bill_qr_close_by
Revises: 0054_add_bill_qr_fields
Create Date: 2026-08-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0055_add_bill_qr_close_by"
down_revision = "0054_add_bill_qr_fields"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    columns = {c["name"] for c in inspect(conn).get_columns("bills")}

    if "razorpay_qr_close_by" not in columns:
        op.add_column("bills", sa.Column("razorpay_qr_close_by", sa.Integer(), nullable=True))


def downgrade():
    conn = op.get_bind()
    columns = {c["name"] for c in inspect(conn).get_columns("bills")}

    if "razorpay_qr_close_by" in columns:
        op.drop_column("bills", "razorpay_qr_close_by")
