"""
Stage 3D hardening — per-install `origin` on allocation / pool / claim rows
(a reinstall restarts local ids at 1 and must not overwrite older rows),
and `bill_number` on claims (so claims of archived bills can be left out of profit).

Revision ID: 0059_sale_allocation_origin
Revises: 0058_add_sale_allocations
Create Date: 2026-10-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0059_sale_allocation_origin"
down_revision = "0058_add_sale_allocations"
branch_labels = None
depends_on = None

_TABLES = [
    ("sale_batch_allocations", "uq_sale_alloc_shop_local", "uq_sale_alloc_shop_origin_local"),
    ("pdn_gone_pools", "uq_pdn_pool_shop_local", "uq_pdn_pool_shop_origin_local"),
    ("cost_correction_claims", "uq_cost_claim_shop_local", "uq_cost_claim_shop_origin_local"),
]


def upgrade():
    conn = op.get_bind()
    insp = inspect(conn)
    for table, old_uq, new_uq in _TABLES:
        cols = {c["name"] for c in insp.get_columns(table)}
        uqs = {u["name"] for u in insp.get_unique_constraints(table)}
        with op.batch_alter_table(table) as b:
            if "origin" not in cols:
                b.add_column(sa.Column("origin", sa.String(40), nullable=False, server_default=""))
            if old_uq in uqs:
                b.drop_constraint(old_uq, type_="unique")
            if new_uq not in uqs:
                b.create_unique_constraint(new_uq, ["shop_id", "origin", "local_id"])
    claim_cols = {c["name"] for c in insp.get_columns("cost_correction_claims")}
    if "bill_number" not in claim_cols:
        op.add_column("cost_correction_claims", sa.Column("bill_number", sa.String, nullable=True))
        op.create_index("ix_cost_correction_claims_bill_number", "cost_correction_claims", ["bill_number"])


def downgrade():
    op.drop_index("ix_cost_correction_claims_bill_number", table_name="cost_correction_claims")
    op.drop_column("cost_correction_claims", "bill_number")
    for table, old_uq, new_uq in _TABLES:
        with op.batch_alter_table(table) as b:
            b.drop_constraint(new_uq, type_="unique")
            b.create_unique_constraint(old_uq, ["shop_id", "local_id"])
            b.drop_column("origin")
