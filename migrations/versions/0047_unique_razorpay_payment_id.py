"""
Adds a unique index on orders.razorpay_payment_id.

Backstop for the order-reconciliation double-activation risk (found
2026-08-14): activate_order()'s idempotency guard is a read-then-write
check on Order.status, not a DB-level constraint. The row-level lock
added to reconcile_stuck_orders() (with_for_update(skip_locked=True))
closes that gap for the reconciliation path specifically, but this
unique index is a second, independent line of defense — if any other
code path (present or future) ever tries to write the same
razorpay_payment_id onto two different Order rows, Postgres rejects the
second write outright instead of silently allowing a duplicate.

Postgres unique indexes allow any number of NULL values (NULL is never
equal to NULL), so this does not affect the many Order rows that never
reach a captured payment (razorpay_payment_id stays NULL for those) —
only genuine duplicate non-NULL values are rejected.

Idempotent (checks index existence first), safe to re-run.

Revision ID: 0047_unique_razorpay_payment_id
Revises: 0046_add_diagnostic_reports_table
Create Date: 2026-08-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0047_unique_razorpay_payment_id"
down_revision = "0046_add_diagnostic_reports_table"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_orders_razorpay_payment_id_unique"


def upgrade():
    conn = op.get_bind()
    existing_indexes = {ix["name"] for ix in inspect(conn).get_indexes("orders")}
    if INDEX_NAME in existing_indexes:
        return
    op.create_index(
        INDEX_NAME,
        "orders",
        ["razorpay_payment_id"],
        unique=True,
    )


def downgrade():
    conn = op.get_bind()
    existing_indexes = {ix["name"] for ix in inspect(conn).get_indexes("orders")}
    if INDEX_NAME not in existing_indexes:
        return
    op.drop_index(INDEX_NAME, table_name="orders")
