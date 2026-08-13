"""
v40 — Categories + Customer master tables.

Ported from app/main.py's _ensure_v40_tables() as part of consolidating the
28 ad-hoc startup ALTER functions into real, ordered Alembic migrations.
The logic below is unchanged from the original function — only the
connection source changed (op.get_bind() instead of a fresh
engine.connect()), so this migration is exactly as idempotent-safe as
the original was, and safe to run against a database that already has
some or all of these columns/tables.

Revision ID: 0028_ensure_v40_tables
Revises: 0027_ensure_global_product_name_unique
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = '0028_ensure_v40_tables'
down_revision = '0027_ensure_global_product_name_unique'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    from app.models.shop_category import ShopCategory
    from app.models.customer import Customer
    ShopCategory.__table__.create(bind=conn, checkfirst=True)
    Customer.__table__.create(bind=conn, checkfirst=True)


def downgrade():
    op.execute(text("DROP TABLE IF EXISTS customers"))
    op.execute(text("DROP TABLE IF EXISTS shop_categories"))
