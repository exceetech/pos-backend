"""
Add cancellation (void) state to bills.

The app has had a local cancel/void flow since v23 (bills.is_cancelled in
Room), but the server bills table had no counterpart: cancellations only
reached GstSalesInvoice, so voided invoices kept counting in analytics
revenue and bill counts forever — and analytics disagreed with GSTR-1.

`active` remains the single switch report queries filter on; is_cancelled
distinguishes a voided bill from a clear-bills archive for audit.

Revision ID: 0007_bill_cancellation
Revises: 0006_money_to_numeric
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '0007_bill_cancellation'
down_revision = '0006_money_to_numeric'
branch_labels = None
depends_on = None


def upgrade():
    # Guard against the case where create_all() already added these columns
    # (fresh-DB startup + alembic upgrade head both running against the same DB).
    from sqlalchemy import inspect, text
    bind = op.get_bind()
    existing = {c["name"] for c in inspect(bind).get_columns("bills")}

    if "is_cancelled" not in existing:
        op.add_column(
            'bills',
            sa.Column('is_cancelled', sa.Boolean, nullable=False,
                      server_default=sa.false())
        )
    if "cancelled_at" not in existing:
        op.add_column(
            'bills',
            sa.Column('cancelled_at', sa.DateTime, nullable=True)
        )


def downgrade():
    op.drop_column('bills', 'cancelled_at')
    op.drop_column('bills', 'is_cancelled')
