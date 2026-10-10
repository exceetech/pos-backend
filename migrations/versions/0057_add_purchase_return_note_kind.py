"""
Purchase correction notes (QDN / PDN), Phase 1 —
purchase_returns.note_kind, rate_delta_net, shelf_value_delta.

  note_kind         NULL (legacy; read as RETURN for D / ADDITION for C),
                    RETURN, ADDITION, QTY_CORRECTION, PRICE_CORRECTION
  rate_delta_net    per-unit NET (taxable) rate change of a price note
  shelf_value_delta the part of a price note that went into the average
                    cost (the "shelf" part); the rest is booked in
                    inventory_valuation_variance

All additive with safe defaults, idempotent (checks existence first).

Revision ID: 0057_add_purchase_return_note_kind
Revises: 0056_add_global_variant_brand
Create Date: 2026-10-09
"""
from alembic import op
from sqlalchemy import inspect, text

revision = "0057_add_purchase_return_note_kind"
down_revision = "0056_add_global_variant_brand"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    if "purchase_returns" not in inspect(conn).get_table_names():
        return
    cols = {c["name"] for c in inspect(conn).get_columns("purchase_returns")}
    if "note_kind" not in cols:
        conn.execute(text("ALTER TABLE purchase_returns ADD COLUMN note_kind VARCHAR(20)"))
    if "rate_delta_net" not in cols:
        conn.execute(text(
            "ALTER TABLE purchase_returns ADD COLUMN rate_delta_net DOUBLE PRECISION NOT NULL DEFAULT 0.0"
        ))
    if "shelf_value_delta" not in cols:
        conn.execute(text(
            "ALTER TABLE purchase_returns ADD COLUMN shelf_value_delta DOUBLE PRECISION NOT NULL DEFAULT 0.0"
        ))


def downgrade():
    conn = op.get_bind()
    conn.execute(text("ALTER TABLE purchase_returns DROP COLUMN IF EXISTS shelf_value_delta"))
    conn.execute(text("ALTER TABLE purchase_returns DROP COLUMN IF EXISTS rate_delta_net"))
    conn.execute(text("ALTER TABLE purchase_returns DROP COLUMN IF EXISTS note_kind"))
