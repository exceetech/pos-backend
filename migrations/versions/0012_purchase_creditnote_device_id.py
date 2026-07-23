"""
Add client_device_id to purchases + credit_notes.

Same idempotency-key pattern already used for bills (see
0005_bill_idempotency_key): the app's local Room id alone isn't unique
across devices on the same shop, so a second device that independently
numbers its own purchase/credit-note "5" would otherwise collide with and
silently overwrite device A's row when matched on (shop_id, local_id)
alone. Adding client_device_id lets the sync endpoints match on
(shop_id, client_device_id, local_id) instead.

Revision ID: 0012_purchase_creditnote_device_id
Revises: 0011_global_variant_autofill
Create Date: 2026-07-23
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '0012_purchase_creditnote_device_id'
down_revision = '0011_global_variant_autofill'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('purchases', sa.Column('client_device_id', sa.String, nullable=True))
    op.create_index(
        'ix_purchases_client_key',
        'purchases',
        ['shop_id', 'client_device_id', 'local_id'],
    )

    op.add_column('credit_notes', sa.Column('client_device_id', sa.String, nullable=True))
    op.create_index(
        'ix_credit_notes_client_key',
        'credit_notes',
        ['shop_id', 'client_device_id', 'local_id'],
    )


def downgrade():
    op.drop_index('ix_credit_notes_client_key', table_name='credit_notes')
    op.drop_column('credit_notes', 'client_device_id')

    op.drop_index('ix_purchases_client_key', table_name='purchases')
    op.drop_column('purchases', 'client_device_id')
