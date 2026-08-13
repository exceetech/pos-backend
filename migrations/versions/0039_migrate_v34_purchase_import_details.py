"""
v34 — purchase_import_details table + purchases.purchase_source.

Ported from app/main.py's _migrate_v34() as part of consolidating the
28 ad-hoc startup ALTER functions into real, ordered Alembic migrations.
The logic below is unchanged from the original function — only the
connection source changed (op.get_bind() instead of a fresh
engine.connect()), so this migration is exactly as idempotent-safe as
the original was, and safe to run against a database that already has
some or all of these columns/tables.

Revision ID: 0039_migrate_v34_purchase_import_details
Revises: 0038_migrate_v33_purchase_returns_gstr_fields
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = '0039_migrate_v34_purchase_import_details'
down_revision = '0038_migrate_v33_purchase_returns_gstr_fields'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    from app.models.purchase_import_details import PurchaseImportDetails
    PurchaseImportDetails.__table__.create(bind=conn, checkfirst=True)

    if "purchases" in inspect(conn).get_table_names():
        cols = {c["name"]: c for c in inspect(conn).get_columns("purchases")}
        if "purchase_source" not in cols:
            conn.execute(text("ALTER TABLE purchases ADD COLUMN purchase_source VARCHAR NOT NULL DEFAULT 'DOMESTIC'"))


def downgrade():
    conn = op.get_bind()
    conn.execute(text("ALTER TABLE purchases DROP COLUMN IF EXISTS purchase_source"))
    op.execute(text("DROP TABLE IF EXISTS purchase_import_details"))
