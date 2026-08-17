"""
Per-shop Razorpay account for "send to customer" UPI payment links.

Every earlier version of this feature used the backend's own global
RAZORPAY_TEST_* env vars for every shop, which would have deposited
every shop's customer payments into one shared account. This corrects
that: each shop connects its own Razorpay account (key id/secret from
their own dashboard, entered in Billing Settings) so payments go
directly to that shop's own bank account.

Idempotent (checks column existence first), safe to re-run.

Revision ID: 0053_add_shop_razorpay_credentials
Revises: 0052_add_bill_payment_link_fields
Create Date: 2026-08-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0053_add_shop_razorpay_credentials"
down_revision = "0052_add_bill_payment_link_fields"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    columns = {c["name"] for c in inspect(conn).get_columns("billing_settings")}

    if "razorpay_key_id" not in columns:
        op.add_column("billing_settings", sa.Column("razorpay_key_id", sa.String(), nullable=True))
    if "razorpay_key_secret" not in columns:
        op.add_column("billing_settings", sa.Column("razorpay_key_secret", sa.String(), nullable=True))
    if "razorpay_webhook_secret" not in columns:
        op.add_column("billing_settings", sa.Column("razorpay_webhook_secret", sa.String(), nullable=True))


def downgrade():
    conn = op.get_bind()
    columns = {c["name"] for c in inspect(conn).get_columns("billing_settings")}

    if "razorpay_webhook_secret" in columns:
        op.drop_column("billing_settings", "razorpay_webhook_secret")
    if "razorpay_key_secret" in columns:
        op.drop_column("billing_settings", "razorpay_key_secret")
    if "razorpay_key_id" in columns:
        op.drop_column("billing_settings", "razorpay_key_id")
