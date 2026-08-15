"""
Adds the missing `address` column to store_gst_profile.

Found 2026-08-15: the SQLAlchemy model (app/models/gst_profile.py) has
defined `address` as a column for some time, but no migration ever
added it — the original 0001_gst_module.py create_table call omitted
it, and no add_column migration was written afterward either. This
went unnoticed because every database this app had run against until
now was originally bootstrapped (at least in part) via
Base.metadata.create_all(), which silently creates whatever columns
the model currently defines — masking the gap. It surfaced for the
first time on a database built strictly from `alembic upgrade head`
with create_all() removed (see 0047 and app/main.py), which is
exactly the schema-drift risk that removal was meant to catch.

Idempotent (checks column existence first), safe to re-run.

Revision ID: 0048_add_store_gst_profile_address
Revises: 0047_unique_razorpay_payment_id
Create Date: 2026-08-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0048_add_store_gst_profile_address"
down_revision = "0047_unique_razorpay_payment_id"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    existing_columns = {c["name"] for c in inspect(conn).get_columns("store_gst_profile")}
    if "address" in existing_columns:
        return
    op.add_column(
        "store_gst_profile",
        sa.Column("address", sa.String(), nullable=False, server_default=""),
    )


def downgrade():
    conn = op.get_bind()
    existing_columns = {c["name"] for c in inspect(conn).get_columns("store_gst_profile")}
    if "address" not in existing_columns:
        return
    op.drop_column("store_gst_profile", "address")
