"""
Convert money columns from double precision (Float) to NUMERIC(12,2).

R3 fix: binary floating point accumulates paise-level drift in SUM/AVG
aggregates as billing data grows. NUMERIC gives exact storage and exact
aggregation. Existing values are rounded to 2 decimals during the cast —
this is the *intended* cleanup of float artifacts (e.g. 99.9000000000001
becomes 99.90).

Quantities (can be fractional kg/L), GST rates (percentages) and counts
deliberately stay as Float.

Revision ID: 0006_money_to_numeric
Revises: 0005_bill_idempotency_key
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '0006_money_to_numeric'
down_revision = '0005_bill_idempotency_key'
branch_labels = None
depends_on = None

MONEY = sa.Numeric(12, 2)

MONEY_COLUMNS = {
    "bills": [
        "subtotal", "discount_amount", "taxable_amount",
        "cgst_amount", "sgst_amount", "igst_amount",
        "cess_amount", "gst_amount",
        "round_off", "final_amount",
    ],
    "bill_items": [
        "unit_price", "line_subtotal", "discount_amount", "taxable_amount",
        "cgst_amount", "sgst_amount", "igst_amount", "cess_amount",
        "total_amount",
    ],
    "credit_notes": [
        "taxable_value", "cgst_amount", "sgst_amount", "igst_amount",
        "cess_amount", "tax_amount", "total_amount",
    ],
    "credit_note_items": [
        "rate", "cost_price_used", "taxable_value",
        "cgst_amount", "sgst_amount", "igst_amount", "cess_amount",
        "tax_amount", "total_amount",
    ],
}


def upgrade():
    for table, columns in MONEY_COLUMNS.items():
        for col in columns:
            op.alter_column(
                table,
                col,
                type_=MONEY,
                existing_type=sa.Float(),
                existing_nullable=False,
                # round float artifacts away during the cast
                postgresql_using=f"round({col}::numeric, 2)",
            )


def downgrade():
    for table, columns in MONEY_COLUMNS.items():
        for col in columns:
            op.alter_column(
                table,
                col,
                type_=sa.Float(),
                existing_type=MONEY,
                existing_nullable=False,
                postgresql_using=f"{col}::double precision",
            )
