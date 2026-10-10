"""
Stage 3D — sale_batch_allocations, pdn_gone_pools, cost_correction_claims.

Additive, idempotent (creates each table only if missing).

Revision ID: 0058_add_sale_allocations
Revises: 0057_add_purchase_return_note_kind
Create Date: 2026-10-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0058_add_sale_allocations"
down_revision = "0057_add_purchase_return_note_kind"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    existing = set(inspect(conn).get_table_names())

    if "sale_batch_allocations" not in existing:
        op.create_table(
            "sale_batch_allocations",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("shop_id", sa.Integer, sa.ForeignKey("shops.id"), nullable=False),
            sa.Column("local_id", sa.Integer, nullable=False),
            sa.Column("source_type", sa.String(24), nullable=False),
            sa.Column("source_id", sa.Integer, nullable=False, server_default="0"),
            sa.Column("bill_number", sa.String, nullable=True),
            sa.Column("line_ordinal", sa.Integer, nullable=True),
            sa.Column("product_id", sa.Integer, nullable=False),
            sa.Column("purchase_invoice_id", sa.Integer, nullable=True),
            sa.Column("batch_local_id", sa.Integer, nullable=True),
            sa.Column("quantity", sa.Float, nullable=False),
            sa.Column("quantity_restored", sa.Float, nullable=False, server_default="0"),
            sa.Column("unit_cost_net", sa.Float, nullable=False, server_default="0"),
            sa.Column("unit_cost_gross", sa.Float, nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime, nullable=True),
            sa.UniqueConstraint("shop_id", "local_id", name="uq_sale_alloc_shop_local"),
        )
        op.create_index("ix_sale_batch_allocations_shop_id", "sale_batch_allocations", ["shop_id"])
        op.create_index("ix_sale_batch_allocations_product_id", "sale_batch_allocations", ["product_id"])
        op.create_index("ix_sale_batch_allocations_purchase_invoice_id", "sale_batch_allocations", ["purchase_invoice_id"])
        op.create_index("ix_sale_batch_allocations_bill_number", "sale_batch_allocations", ["bill_number"])

    if "pdn_gone_pools" not in existing:
        op.create_table(
            "pdn_gone_pools",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("shop_id", sa.Integer, sa.ForeignKey("shops.id"), nullable=False),
            sa.Column("local_id", sa.Integer, nullable=False),
            sa.Column("note_local_id", sa.Integer, nullable=False),
            sa.Column("purchase_invoice_id", sa.Integer, nullable=False),
            sa.Column("product_id", sa.Integer, nullable=False),
            sa.Column("gone_qty", sa.Float, nullable=False),
            sa.Column("delta_gross", sa.Float, nullable=False),
            sa.Column("note_date", sa.DateTime, nullable=False),
            sa.UniqueConstraint("shop_id", "local_id", name="uq_pdn_pool_shop_local"),
        )
        op.create_index("ix_pdn_gone_pools_shop_id", "pdn_gone_pools", ["shop_id"])
        op.create_index("ix_pdn_gone_pools_purchase_invoice_id", "pdn_gone_pools", ["purchase_invoice_id"])

    if "cost_correction_claims" not in existing:
        op.create_table(
            "cost_correction_claims",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("shop_id", sa.Integer, sa.ForeignKey("shops.id"), nullable=False),
            sa.Column("local_id", sa.Integer, nullable=False),
            sa.Column("allocation_local_id", sa.Integer, nullable=False),
            sa.Column("pool_local_id", sa.Integer, nullable=False),
            sa.Column("note_local_id", sa.Integer, nullable=False),
            sa.Column("product_id", sa.Integer, nullable=True),
            sa.Column("qty", sa.Float, nullable=False),
            sa.Column("amount", sa.Float, nullable=False),
            sa.Column("claim_date", sa.DateTime, nullable=False),
            sa.Column("source_type", sa.String(16), nullable=False),
            sa.Column("source_id", sa.Integer, nullable=False, server_default="0"),
            sa.UniqueConstraint("shop_id", "local_id", name="uq_cost_claim_shop_local"),
        )
        op.create_index("ix_cost_correction_claims_shop_id", "cost_correction_claims", ["shop_id"])
        op.create_index("ix_cost_correction_claims_product_id", "cost_correction_claims", ["product_id"])
        op.create_index("ix_cost_correction_claims_claim_date", "cost_correction_claims", ["claim_date"])


def downgrade():
    op.drop_table("cost_correction_claims")
    op.drop_table("pdn_gone_pools")
    op.drop_table("sale_batch_allocations")
