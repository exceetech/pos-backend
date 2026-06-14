"""
Add client_bill_id + client_device_id to bills.

Idempotency key for /bills/create: the app's local Room bill id and
device id. Prevents a retried or concurrent sync from inserting the
same sale twice (seen as duplicate entries for composition-scheme
shops where the save flow and the dashboard sync raced each other).

Revision ID: 0005_bill_idempotency_key
Revises: 0004_supply_classification
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '0005_bill_idempotency_key'
down_revision = '0004_supply_classification'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('bills', sa.Column('client_bill_id', sa.Integer, nullable=True))
    op.add_column('bills', sa.Column('client_device_id', sa.String, nullable=True))
    op.create_index(
        'ix_bills_client_key',
        'bills',
        ['shop_id', 'client_device_id', 'client_bill_id'],
    )


def downgrade():
    op.drop_index('ix_bills_client_key', table_name='bills')
    op.drop_column('bills', 'client_device_id')
    op.drop_column('bills', 'client_bill_id')
