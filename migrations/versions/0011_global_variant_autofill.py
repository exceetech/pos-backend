"""
Global variant autofill fields + uniqueness

Revision ID: 0011_global_variant_autofill
Revises: 0010_purchase_discount
Create Date: 2026-07-04

What this migration does:
1. De-duplicates existing (product_id, variant_name) rows in
   global_product_variants — MUST run before the unique constraint,
   otherwise create_unique_constraint aborts on legacy duplicates.
   Keeps the verified row when present, else the lowest id.
2. Adds provenance + statutory autofill columns
   (created_by_shop_id, hsn_code, default_gst_rate, cgst/sgst/igst,
   cess_rate). Floats get a server_default of 0 so existing rows
   backfill cleanly. Price is intentionally NOT added.
3. Adds UniqueConstraint(product_id, variant_name).
"""
from alembic import op
import sqlalchemy as sa


revision = '0011_global_variant_autofill'
down_revision = '0010_purchase_discount'
branch_labels = None
depends_on = None


def upgrade():
    dialect = op.get_bind().dialect.name

    # 1. De-duplicate FIRST (keep verified, else lowest id) ----------
    if dialect == "postgresql":
        op.execute(
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
            WHERE g.id = d.id AND d.rn > 1;
            """
        )
    else:
        # Portable form (SQLite/MySQL) — keeps the lowest id per group.
        op.execute(
            """
            DELETE FROM global_product_variants
            WHERE id NOT IN (
                SELECT MIN(id) FROM global_product_variants
                GROUP BY product_id, variant_name
            );
            """
        )

    # 2. Add new columns --------------------------------------------
    # Guarded (2026-08-15): global_product_variants is created by the
    # baseline migration (0000_baseline_schema) from today's model, which
    # already includes these columns and constraints — existence checks
    # make this a safe no-op on a fresh database.
    from sqlalchemy import inspect
    bind = op.get_bind()
    existing = {c["name"] for c in inspect(bind).get_columns("global_product_variants")}

    def add_if_missing(col_name, column):
        if col_name not in existing:
            op.add_column('global_product_variants', column)

    add_if_missing('created_by_shop_id', sa.Column('created_by_shop_id', sa.Integer(), nullable=True))
    add_if_missing('hsn_code', sa.Column('hsn_code', sa.String(), nullable=True))
    add_if_missing('hsn_description', sa.Column('hsn_description', sa.String(), nullable=True))
    add_if_missing('official_uqc', sa.Column('official_uqc', sa.String(), nullable=True))
    add_if_missing('default_gst_rate', sa.Column('default_gst_rate', sa.Float(), server_default='0', nullable=True))
    add_if_missing('cgst_percentage', sa.Column('cgst_percentage', sa.Float(), server_default='0', nullable=True))
    add_if_missing('sgst_percentage', sa.Column('sgst_percentage', sa.Float(), server_default='0', nullable=True))
    add_if_missing('igst_percentage', sa.Column('igst_percentage', sa.Float(), server_default='0', nullable=True))
    add_if_missing('cess_rate', sa.Column('cess_rate', sa.Float(), server_default='0', nullable=True))

    # 3. FK + uniqueness. SQLite cannot ALTER-ADD a constraint, so use
    #    batch mode there and skip the FK (unsupported via ALTER).
    existing_uniques = {uc["name"] for uc in inspect(bind).get_unique_constraints("global_product_variants")}
    # Check by constrained column, not by name — a table created via
    # create_all() from the current model (which declares this FK
    # without an explicit name) gets a Postgres auto-generated name, not
    # 'fk_gpv_created_by_shop', so a name-only check would create a
    # harmless-but-messy duplicate constraint on a fresh database.
    fk_already_exists = any(
        fk["constrained_columns"] == ["created_by_shop_id"]
        for fk in inspect(bind).get_foreign_keys("global_product_variants")
    )

    if dialect == "sqlite":
        if 'uix_gpv_product_variant' not in existing_uniques:
            with op.batch_alter_table('global_product_variants') as batch:
                batch.create_unique_constraint(
                    'uix_gpv_product_variant', ['product_id', 'variant_name']
                )
    else:
        if not fk_already_exists:
            op.create_foreign_key(
                'fk_gpv_created_by_shop',
                'global_product_variants', 'shops',
                ['created_by_shop_id'], ['id'],
            )
        if 'uix_gpv_product_variant' not in existing_uniques:
            op.create_unique_constraint(
                'uix_gpv_product_variant',
                'global_product_variants',
                ['product_id', 'variant_name'],
            )


def downgrade():
    dialect = op.get_bind().dialect.name

    if dialect == "sqlite":
        with op.batch_alter_table('global_product_variants') as batch:
            batch.drop_constraint('uix_gpv_product_variant', type_='unique')
    else:
        op.drop_constraint('uix_gpv_product_variant',
                           'global_product_variants', type_='unique')
        op.drop_constraint('fk_gpv_created_by_shop',
                           'global_product_variants', type_='foreignkey')

    op.drop_column('global_product_variants', 'cess_rate')
    op.drop_column('global_product_variants', 'igst_percentage')
    op.drop_column('global_product_variants', 'sgst_percentage')
    op.drop_column('global_product_variants', 'cgst_percentage')
    op.drop_column('global_product_variants', 'default_gst_rate')
    op.drop_column('global_product_variants', 'official_uqc')
    op.drop_column('global_product_variants', 'hsn_description')
    op.drop_column('global_product_variants', 'hsn_code')
    op.drop_column('global_product_variants', 'created_by_shop_id')
