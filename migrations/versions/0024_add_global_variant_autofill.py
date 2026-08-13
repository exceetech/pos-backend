"""
global_product_variants: provenance + statutory tax columns, plus
the (product_id, variant_name) uniqueness constraint (dedup first).

Ported from app/main.py's _add_global_variant_autofill() as part of consolidating the
28 ad-hoc startup ALTER functions into real, ordered Alembic migrations.
The logic below is unchanged from the original function — only the
connection source changed (op.get_bind() instead of a fresh
engine.connect()), so this migration is exactly as idempotent-safe as
the original was, and safe to run against a database that already has
some or all of these columns/tables.

Revision ID: 0024_add_global_variant_autofill
Revises: 0023_drop_legacy_gst_sales_records_table
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = '0024_add_global_variant_autofill'
down_revision = '0023_drop_legacy_gst_sales_records_table'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    table = "global_product_variants"
    inspector = inspect(conn)
    if table not in set(inspector.get_table_names()):
        return

    column_defs = [
        ("created_by_shop_id", "created_by_shop_id INTEGER NULL"),
        ("hsn_code",           "hsn_code VARCHAR NULL"),
        ("hsn_description",    "hsn_description VARCHAR NULL"),
        ("official_uqc",       "official_uqc VARCHAR NULL"),
        ("default_gst_rate",   "default_gst_rate DOUBLE PRECISION NOT NULL DEFAULT 0.0"),
        ("cgst_percentage",    "cgst_percentage DOUBLE PRECISION NOT NULL DEFAULT 0.0"),
        ("sgst_percentage",    "sgst_percentage DOUBLE PRECISION NOT NULL DEFAULT 0.0"),
        ("igst_percentage",    "igst_percentage DOUBLE PRECISION NOT NULL DEFAULT 0.0"),
        ("cess_rate",          "cess_rate DOUBLE PRECISION NOT NULL DEFAULT 0.0"),
    ]

    dialect = conn.engine.dialect.name

    existing = {c["name"] for c in inspector.get_columns(table)}
    for column_name, ddl in column_defs:
        if column_name not in existing:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))
            existing.add(column_name)

    if dialect == "postgresql":
        conn.execute(text(
            """
            DELETE FROM global_product_variants g
            USING (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY product_id, variant_name
                           ORDER BY is_verified DESC, id ASC
                       ) AS rn
                FROM global_product_variants
            ) d
            WHERE g.id = d.id AND d.rn > 1
            """
        ))
    else:
        conn.execute(text(
            """
            DELETE FROM global_product_variants
            WHERE id NOT IN (
                SELECT MIN(id) FROM global_product_variants
                GROUP BY product_id, variant_name
            )
            """
        ))

    if dialect != "sqlite":
        constraint_names = {
            uc["name"] for uc in inspect(conn).get_unique_constraints(table)
        }
        if "uix_gpv_product_variant" not in constraint_names:
            conn.execute(text(
                "ALTER TABLE global_product_variants "
                "ADD CONSTRAINT uix_gpv_product_variant "
                "UNIQUE (product_id, variant_name)"
            ))


def downgrade():
    conn = op.get_bind()
    if conn.engine.dialect.name != "sqlite":
        conn.execute(text(
            "ALTER TABLE global_product_variants "
            "DROP CONSTRAINT IF EXISTS uix_gpv_product_variant"
        ))
    # Column drops and the dedup DELETE are not reversed — the dedup is
    # inherently destructive (duplicate rows are gone for good) and column
    # drops here would risk breaking later migrations that also touch this
    # table. Restore from backup if full reversal is required.
