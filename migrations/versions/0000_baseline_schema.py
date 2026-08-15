"""
Baseline schema — creates every core table that was historically created
only by `Base.metadata.create_all(bind=engine)` in app/main.py, never by
an Alembic migration.

Why this exists (found 2026-08-15): `create_all()` was removed from
main.py as part of a hosting-readiness fix (see DATABASE_MIGRATIONS_GUIDE.md
2026-08-14 update) on the reasoning that Alembic's 46+ migrations were
"the sole source of schema truth." That was true for every table added
SINCE Alembic was introduced (store_gst_profile, gst_purchase_records,
bills, bill_items, purchase_batches, shop_categories, customers,
suppliers, credit_notes, credit_note_items, purchase_import_details,
user_event_logs, diagnostic_reports — all covered by 0001/0015/0016/
0028/0029/0031/0039/0045/0046). It was NOT true for the tables that
already existed before Alembic was ever added to this project — those
were only ever created by create_all() reading live SQLAlchemy model
metadata, and were never captured as a migration of their own. Removing
create_all() silently broke the ability to bootstrap a genuinely fresh,
empty database: `alembic upgrade head` would reach migration 0001 and
fail immediately, since 0001 assumes `shops` (and everything else below)
already exists.

Every real deployment so far already has these 26 tables (created by the
now-removed create_all() at some point in the past), so this migration
is a no-op there — checkfirst=True on every table means it only ever
creates what's actually missing. Its entire purpose is to make a
brand-new, empty database (e.g. a fresh Cloud SQL test/staging instance)
reach the exact same schema as every existing deployment via a single
`alembic upgrade head`, restoring the guarantee
DATABASE_MIGRATIONS_GUIDE.md already claims.

Uses Base.metadata.create_all(..., tables=[...]) rather than creating
each table by hand: passing an explicit `tables=` subset still gets
SQLAlchemy's automatic foreign-key dependency sorting (e.g. shops before
shop_products, purchases before purchase_items), so table order here
doesn't need to be hand-maintained — it's derived from the models
themselves, same way create_all() always worked.

Revision ID: 0000_baseline_schema
Revises: (base)
Create Date: 2026-08-15
"""
from alembic import op
import sqlalchemy as sa

# All 33 model modules live under app.models; importing the package (as
# migrations/env.py already does before invoking any migration) is what
# populates Base.metadata — this migration only needs to select the
# subset of tables not already covered by a later migration.
from app.database import Base
import app.models  # noqa: F401 — ensure every model is registered

revision = '0000_baseline_schema'
down_revision = None
branch_labels = None
depends_on = None

# Every table NOT created by any other migration (0001, 0015, 0016,
# 0028, 0029, 0031, 0039, 0045, 0046) — see this file's docstring for
# how this list was derived. Table creation ORDER is not hand-specified
# here; Base.metadata.create_all() topologically sorts by foreign key
# automatically when given this list via `tables=`.
BASELINE_TABLES = [
    "app_config",
    "audit_logs",
    "billing_settings",
    "coupons",
    "coupon_redemptions",
    "credit_accounts",
    "credit_transactions",
    "global_hsn",
    "global_product_variants",
    "global_products",
    "gst_sales_invoice",
    "gst_sales_invoice_items",
    "import_services",
    "inventory",
    "inventory_logs",
    "orders",
    "plans",
    "processed_webhook_events",
    "purchases",
    "purchase_items",
    "purchase_returns",
    "sale_items",
    "scrap_entries",
    "shops",
    "shop_products",
    "subscriptions",
    # bills, bill_items, credit_notes, credit_note_items (2026-08-15):
    # these ARE also created later by 0015/0031 respectively (both
    # checkfirst=True, so no conflict there), but earlier migrations —
    # 0005/0007 (bills), 0012 (credit_notes) — already need these tables
    # to exist well before 0015/0031 run. Including them here too closes
    # that ordering gap; 0015/0031 simply no-op on them later since the
    # tables already exist.
    "bills",
    "bill_items",
    "credit_notes",
    "credit_note_items",
]


def upgrade():
    conn = op.get_bind()

    # Widen alembic_version.version_num BEFORE anything else in this
    # migration (found 2026-08-15, running this migration for the first
    # time against a genuinely fresh database). Alembic auto-creates this
    # tracking table itself with a hardcoded VARCHAR(32) column — fine for
    # short hash-style revision ids, but this project's migrations use
    # long descriptive names instead. 17 revision ids in this project's
    # history exceed 32 characters (e.g. '0012_purchase_creditnote_device_id'
    # at 34, up to 49 for the longest), so without this, Alembic would
    # fail immediately after successfully running EVERY one of those 17
    # migrations — not because the migration's own DDL is wrong, but
    # because Alembic's own bookkeeping step right after it (recording
    # "we're now at this revision") can't fit the id into 32 characters.
    # Widening this once, right at the start, avoids hitting that same
    # failure 17 separate times on the way to head.
    conn.execute(
        sa.text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)")
    )

    tables = [
        Base.metadata.tables[name]
        for name in BASELINE_TABLES
        if name in Base.metadata.tables
    ]
    Base.metadata.create_all(bind=conn, checkfirst=True, tables=tables)


def downgrade():
    # Deliberately a no-op, same reasoning as 0015/0016/0028/0029/0031/
    # 0039's downgrades: these are core tables holding real business
    # data (shops, purchases, inventory, subscriptions...) on every
    # existing deployment. Dropping them here would be catastrophic if
    # this downgrade were ever run against a real database by mistake.
    # A pre-upgrade backup is the real safety net, not downgrade().
    pass
