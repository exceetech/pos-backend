from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base

from app.models import *

# Registers SQLAlchemy listeners that auto-invalidate the AI caches on relevant writes.
from app.util import ai_cache_hooks  # noqa: F401

from app.routes import auth_routes, profit_routes, sales_routes
from app.routes import product_routes
from app.routes import bill_routes
from app.routes import report_routes
from app.routes import shop_routes
from app.routes import billing_settings_routes
from app.routes.security_routes import router as security_router
from app.routes import admin_routes
from app.routes.admin_catalog_routes import router as admin_catalog_router
from app.routes.analytics_routes import router as analytics_router
from app.routes import subscription_routes as subscription
from app.routes import gst_routes
from app.routes.global_catalog_routes import router as global_catalog_router
from app.routes.purchase_routes import router as purchase_router
from app.routes.purchase_return_routes import router as purchase_return_router
from app.routes.scrap_routes import router as scrap_router
from app.routes.gst_sales_invoice_routes import router as gst_sales_invoice_router
from app.routes.purchase_batch_routes import router as purchase_batch_router
from app.routes.credit_note_routes import router as credit_note_router



from apscheduler.schedulers.background import BackgroundScheduler
from app.database import SessionLocal
from app.services.expiry_service import check_subscriptions
from app.routes import credit_routes as credit

from app.routes import inventory_routes



app = FastAPI(
    title="POS Backend",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create tables
Base.metadata.create_all(bind=engine)

# ──────────────────────────────────────────────────────────────────────
# Belt-and-braces: explicitly ensure `bills` and `bill_items` tables
# exist.  create_all() is idempotent and handles these, but on some
# deployments where models are imported late (after create_all runs)
# the bills table is silently skipped.  Calling .create(checkfirst=True)
# here guarantees the table is always present before the first request.
# ──────────────────────────────────────────────────────────────────────
def _ensure_bills_table() -> None:
    from app.models.bill import Bill
    from app.models.bill_items import BillItem
    Bill.__table__.create(bind=engine, checkfirst=True)
    BillItem.__table__.create(bind=engine, checkfirst=True)

try:
    _ensure_bills_table()
except Exception as e:
    print(f"[startup] bills table ensure skipped: {e}")

# ──────────────────────────────────────────────────────────────────────
# Hybrid-inventory: ensure `purchase_batches` exists on deployed DBs.
# Base.metadata.create_all is idempotent (won't recreate existing), so
# this is a belt-and-braces explicit log for v20+ rollouts. No ALTER
# is needed because the table is brand-new.
# ──────────────────────────────────────────────────────────────────────
def _ensure_purchase_batches_table() -> None:
    from sqlalchemy import inspect
    insp = inspect(engine)
    if "purchase_batches" not in insp.get_table_names():
        from app.models.purchase_batch import PurchaseBatch
        PurchaseBatch.__table__.create(bind=engine, checkfirst=True)

try:
    _ensure_purchase_batches_table()
except Exception as e:
    print(f"[startup] purchase_batches table ensure skipped: {e}")

# ──────────────────────────────────────────────────────────────────────
# In-place migration: ensure `purchases.invoice_date` exists on already-
# deployed databases. `Base.metadata.create_all` only *creates* missing
# tables, it never ALTERs existing ones — so for the invoice-date
# feature we run an idempotent ALTER once at startup.
#
# Safe to run on a fresh DB (the column will already exist from
# create_all and the ALTER is a no-op). Safe to run repeatedly.
# ──────────────────────────────────────────────────────────────────────
def _add_invoice_date_column() -> None:
    from sqlalchemy import inspect, text

    with engine.connect() as conn:
        cols = {c["name"] for c in inspect(engine).get_columns("purchases")}
        if "invoice_date" in cols:
            return
        # `purchases` exists but the column doesn't — run a generic ALTER
        # that works on Postgres / MySQL / SQLite alike.
        conn.execute(text("ALTER TABLE purchases ADD COLUMN invoice_date TIMESTAMP NULL"))
        conn.commit()

try:
    _add_invoice_date_column()
except Exception as e:  # pragma: no cover — never crash startup
    print(f"[startup] invoice_date migration skipped: {e}")


# ──────────────────────────────────────────────────────────────────────
# In-place migration: add `is_credit` + `credit_account_id` columns to
# the purchases table on already-deployed databases. Idempotent.
# ──────────────────────────────────────────────────────────────────────
def _add_credit_columns_to_purchases() -> None:
    from sqlalchemy import inspect, text
    cols_to_add = {
        "is_credit":         "ALTER TABLE purchases ADD COLUMN is_credit INTEGER NOT NULL DEFAULT 0",
        "credit_account_id": "ALTER TABLE purchases ADD COLUMN credit_account_id INTEGER NULL",
    }
    with engine.connect() as conn:
        existing = {c["name"] for c in inspect(engine).get_columns("purchases")}
        for col, sql in cols_to_add.items():
            if col not in existing:
                conn.execute(text(sql))
        conn.commit()

def _add_sync_idempotency_columns() -> None:
    """Idempotency keys for offline-replay dedupe (Sync audit S2):
       • purchase_returns.local_id  — dedupe debit-note pushes on (shop_id, local_id)
       • inventory_logs.client_uid  — dedupe inventory pushes on a stable client key
       Idempotent; safe on fresh DBs (create_all already added it) and repeats."""
    from sqlalchemy import inspect, text
    targets = {
        "purchase_returns": ("local_id",
            "ALTER TABLE purchase_returns ADD COLUMN local_id INTEGER NULL"),
        "inventory_logs": ("client_uid",
            "ALTER TABLE inventory_logs ADD COLUMN client_uid VARCHAR NULL"),
    }
    with engine.connect() as conn:
        inspector = inspect(engine)
        for table, (col, sql) in targets.items():
            existing = {c["name"] for c in inspector.get_columns(table)}
            if col not in existing:
                conn.execute(text(sql))
        conn.commit()

try:
    _add_sync_idempotency_columns()
except Exception as e:  # pragma: no cover — never crash startup
    print(f"[startup] sync idempotency migration skipped: {e}")


def _add_delta_cursor_columns() -> None:
    """Server-set updated_at cursors for delta pulls (Sync audit S5).

    Adds the column, then backfills existing rows to the current time so a
    first delta pull (updated_since=0) still returns them — without a backfill,
    NULL updated_at would be excluded by the `>=` filter and rows would vanish.
    CURRENT_TIMESTAMP works on SQLite and Postgres. Idempotent."""
    from sqlalchemy import inspect, text
    specs = [
        ("inventory", "updated_at",
         "ALTER TABLE inventory ADD COLUMN updated_at TIMESTAMP NULL",
         "UPDATE inventory SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL"),
        ("purchases", "updated_at",
         "ALTER TABLE purchases ADD COLUMN updated_at TIMESTAMP NULL",
         "UPDATE purchases SET updated_at = COALESCE(created_at, CURRENT_TIMESTAMP) "
         "WHERE updated_at IS NULL"),
        ("bills", "updated_at",
         "ALTER TABLE bills ADD COLUMN updated_at TIMESTAMP NULL",
         "UPDATE bills SET updated_at = COALESCE(created_at, CURRENT_TIMESTAMP) "
         "WHERE updated_at IS NULL"),
    ]
    with engine.connect() as conn:
        inspector = inspect(engine)
        for table, col, add_sql, backfill_sql in specs:
            existing = {c["name"] for c in inspector.get_columns(table)}
            if col not in existing:
                conn.execute(text(add_sql))
                conn.execute(text(backfill_sql))
        conn.commit()

try:
    _add_delta_cursor_columns()
except Exception as e:  # pragma: no cover — never crash startup
    print(f"[startup] delta cursor migration skipped: {e}")


try:
    _add_credit_columns_to_purchases()
except Exception as e:  # pragma: no cover
    print(f"[startup] credit-columns migration skipped: {e}")


# ──────────────────────────────────────────────────────────────────────
# In-place migration: add columns introduced after the original tables
# already existed. SQLAlchemy create_all() never ALTERs existing tables,
# so deployed/local Postgres databases otherwise crash with
# UndefinedColumn as soon as the ORM model selects the new fields.
# ──────────────────────────────────────────────────────────────────────
def _add_column_if_missing(conn, table_name: str, existing: set[str], column_name: str, ddl: str) -> None:
    from sqlalchemy import text

    if column_name not in existing:
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {ddl}"))
        existing.add(column_name)


def _add_gstr_support_columns() -> None:
    from sqlalchemy import inspect, text

    columns_by_table = {
        "shop_products": [
            ("cgst_percentage", "cgst_percentage DOUBLE PRECISION NOT NULL DEFAULT 0.0"),
            ("sgst_percentage", "sgst_percentage DOUBLE PRECISION NOT NULL DEFAULT 0.0"),
            ("igst_percentage", "igst_percentage DOUBLE PRECISION NOT NULL DEFAULT 0.0"),
            ("official_uqc", "official_uqc VARCHAR NULL"),
            ("hsn_description", "hsn_description VARCHAR NULL"),
            ("cess_rate", "cess_rate DOUBLE PRECISION NOT NULL DEFAULT 0.0"),
            ("supply_classification", "supply_classification VARCHAR NOT NULL DEFAULT 'TAXABLE'"),
            ("category", "category VARCHAR NULL DEFAULT ''"),
        ],
        "gst_sales_invoice": [
            ("invoice_number", "invoice_number VARCHAR NULL DEFAULT ''"),
            ("invoice_date", "invoice_date BIGINT NULL DEFAULT 0"),
            ("reverse_charge", "reverse_charge VARCHAR NOT NULL DEFAULT 'N'"),
            ("gstr_invoice_type", "gstr_invoice_type VARCHAR NOT NULL DEFAULT 'Regular'"),
            ("customer_state_code", "customer_state_code VARCHAR NULL"),
            ("ecommerce_gstin", "ecommerce_gstin VARCHAR NULL"),
            ("ecommerce_operator_name", "ecommerce_operator_name VARCHAR NULL"),
            ("eco_nature_of_supply", "eco_nature_of_supply VARCHAR NULL"),
            ("eco_document_type", "eco_document_type VARCHAR NULL"),
            ("eco_supplier_gstin", "eco_supplier_gstin VARCHAR NULL"),
            ("eco_supplier_name", "eco_supplier_name VARCHAR NULL"),
            ("eco_recipient_gstin", "eco_recipient_gstin VARCHAR NULL"),
            ("eco_recipient_name", "eco_recipient_name VARCHAR NULL"),
            ("eco_role", "eco_role VARCHAR NULL"),
            ("is_cancelled", "is_cancelled BOOLEAN NOT NULL DEFAULT FALSE"),
            ("cancelled_at", "cancelled_at TIMESTAMP NULL"),
        ],
        "gst_sales_invoice_items": [
            ("cess_rate", "cess_rate DOUBLE PRECISION NOT NULL DEFAULT 0.0"),
            ("cess_amount", "cess_amount DOUBLE PRECISION NOT NULL DEFAULT 0.0"),
            ("uqc", "uqc VARCHAR NULL"),
            ("hsn_description", "hsn_description VARCHAR NULL"),
        ],
        "bills": [
            # Idempotency key (duplicate-bill guard): the app's local Room
            # bill id + device id. /bills/create dedupes on these.
            ("client_bill_id",  "client_bill_id INTEGER NULL"),
            ("client_device_id","client_device_id VARCHAR NULL"),
            # Cancellation (void) state — added when N1/cancellation support
            # was deployed. create_all() adds these on fresh DBs; this ALTER
            # covers already-deployed databases where create_all() ran with
            # the old model and these columns are therefore missing.
            ("is_cancelled",  "is_cancelled BOOLEAN NOT NULL DEFAULT FALSE"),
            ("cancelled_at",  "cancelled_at TIMESTAMP NULL"),
            # created_at — used for timezone-correct period filtering in reports.
            ("created_at",    "created_at TIMESTAMP NULL"),
            # active — kept separate from is_cancelled (void vs. archive).
            ("active",        "active BOOLEAN DEFAULT TRUE"),
        ],
        "gst_sales_records": [
            ("customer_name", "customer_name VARCHAR NULL"),
            ("business_name", "business_name VARCHAR NULL"),
            ("customer_phone", "customer_phone VARCHAR NULL"),
            ("customer_state", "customer_state VARCHAR NULL"),
            ("customer_state_code", "customer_state_code VARCHAR NULL"),
            ("reverse_charge", "reverse_charge VARCHAR NOT NULL DEFAULT 'N'"),
            ("gstr_invoice_type", "gstr_invoice_type VARCHAR NOT NULL DEFAULT 'Regular'"),
            ("ecommerce_gstin", "ecommerce_gstin VARCHAR NULL"),
            ("ecommerce_operator_name", "ecommerce_operator_name VARCHAR NULL"),
            ("eco_nature_of_supply", "eco_nature_of_supply VARCHAR NULL"),
            ("eco_document_type", "eco_document_type VARCHAR NULL"),
            ("eco_supplier_gstin", "eco_supplier_gstin VARCHAR NULL"),
            ("eco_supplier_name", "eco_supplier_name VARCHAR NULL"),
            ("eco_recipient_gstin", "eco_recipient_gstin VARCHAR NULL"),
            ("eco_recipient_name", "eco_recipient_name VARCHAR NULL"),
            ("eco_role", "eco_role VARCHAR NULL"),
            ("cess_rate", "cess_rate DOUBLE PRECISION NOT NULL DEFAULT 0.0"),
            ("cess_amount", "cess_amount DOUBLE PRECISION NOT NULL DEFAULT 0.0"),
            ("uqc", "uqc VARCHAR NULL"),
            ("hsn_description", "hsn_description VARCHAR NULL"),
            ("is_cancelled", "is_cancelled BOOLEAN NOT NULL DEFAULT FALSE"),
        ],
    }

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.connect() as conn:
        for table_name, column_defs in columns_by_table.items():
            if table_name not in existing_tables:
                continue
            existing = {c["name"] for c in inspector.get_columns(table_name)}
            for column_name, ddl in column_defs:
                _add_column_if_missing(conn, table_name, existing, column_name, ddl)

        # Lookup index for the bill idempotency key.
        if "bills" in existing_tables:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_bills_client_key "
                "ON bills (shop_id, client_device_id, client_bill_id)"
            ))
        conn.commit()


try:
    _add_gstr_support_columns()
except Exception as e:  # pragma: no cover
    print(f"[startup] GSTR support column migration skipped: {e}")


# ──────────────────────────────────────────────────────────────────────
# Global-variant autofill (provenance + statutory tax fields) + the
# (product_id, variant_name) uniqueness that stops duplicate-queue spam.
# create_all() adds all of this on fresh DBs; this idempotent ALTER
# covers already-deployed databases where the table pre-existed. The
# de-dup MUST run before the unique constraint or the ADD CONSTRAINT
# aborts on legacy duplicates.
# ──────────────────────────────────────────────────────────────────────
def _add_global_variant_autofill() -> None:
    from sqlalchemy import inspect, text

    table = "global_product_variants"
    inspector = inspect(engine)
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

    dialect = engine.dialect.name

    with engine.connect() as conn:
        existing = {c["name"] for c in inspector.get_columns(table)}
        for column_name, ddl in column_defs:
            _add_column_if_missing(conn, table, existing, column_name, ddl)

        # De-duplicate (keep verified, else lowest id) BEFORE uniqueness.
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

        # Add the unique constraint only if it isn't already present.
        # (SQLite can't ALTER-ADD a constraint; skip there — create_all
        # already builds it on fresh SQLite dev DBs from the model.)
        if dialect != "sqlite":
            constraint_names = {
                uc["name"] for uc in inspect(engine).get_unique_constraints(table)
            }
            if "uix_gpv_product_variant" not in constraint_names:
                conn.execute(text(
                    "ALTER TABLE global_product_variants "
                    "ADD CONSTRAINT uix_gpv_product_variant "
                    "UNIQUE (product_id, variant_name)"
                ))

        conn.commit()


try:
    _add_global_variant_autofill()
except Exception as e:  # pragma: no cover — never crash startup
    print(f"[startup] global-variant autofill migration skipped: {e}")


# ──────────────────────────────────────────────────────────────────────
# sale_items.bill_number — the SaleItem model declares this column (it is
# stamped with the client's LOCAL-… reference at insert time, then bulk-
# updated to the server INV_YYYY_N number inside create_bill). create_all()
# adds it on fresh DBs; this idempotent ALTER covers already-deployed
# databases whose sale_items table predates the column. Without it,
# create_bill's UPDATE sale_items SET bill_number=… raises UndefinedColumn.
# ──────────────────────────────────────────────────────────────────────
def _add_sale_items_bill_number() -> None:
    from sqlalchemy import inspect, text

    table = "sale_items"
    inspector = inspect(engine)
    if table not in set(inspector.get_table_names()):
        return

    with engine.connect() as conn:
        existing = {c["name"] for c in inspector.get_columns(table)}
        _add_column_if_missing(
            conn, table, existing, "bill_number", "bill_number VARCHAR NULL"
        )

        # Index the reconciliation lookup (create_bill filters on it).
        index_names = {ix["name"] for ix in inspect(engine).get_indexes(table)}
        if "ix_sale_items_bill_number" not in index_names:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_sale_items_bill_number "
                "ON sale_items (bill_number)"
            ))

        conn.commit()


try:
    _add_sale_items_bill_number()
except Exception as e:  # pragma: no cover — never crash startup
    print(f"[startup] sale_items.bill_number migration skipped: {e}")


# ──────────────────────────────────────────────────────────────────────
# Ensure global_products.name is UNIQUE on already-deployed DBs. The model
# declares unique=True (so create_all builds it on fresh DBs), but a DB
# created before that was added won't have it. A single row per name is
# what keeps the app's catalog name→id mapping unambiguous. Best-effort:
# if legacy exact-duplicate names exist the index creation fails and we
# log it (the app's name-based multi-id variant fetch still copes).
# ──────────────────────────────────────────────────────────────────────
def _ensure_global_product_name_unique() -> None:
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "global_products" not in set(inspector.get_table_names()):
        return

    has_unique = (
        any("name" in uc.get("column_names", [])
            for uc in inspector.get_unique_constraints("global_products"))
        or any(ix.get("unique") and ix.get("column_names") == ["name"]
               for ix in inspector.get_indexes("global_products"))
    )
    if has_unique:
        return

    with engine.connect() as conn:
        try:
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uix_global_products_name "
                "ON global_products (name)"
            ))
            conn.commit()
        except Exception as e:
            conn.rollback()
            print("[startup] could not add unique index on "
                  f"global_products.name (duplicate names present?): {e}")


try:
    _ensure_global_product_name_unique()
except Exception as e:  # pragma: no cover — never crash startup
    print(f"[startup] global_products name-uniqueness ensure skipped: {e}")


# ──────────────────────────────────────────────────────────────────────
# v40 — Categories + Customer master. create_all() makes the two new
# tables; this explicit ensure covers already-deployed DBs where
# create_all() ran before these models existed. The shop_products.category
# column is handled by _add_gstr_support_columns above.
# ──────────────────────────────────────────────────────────────────────
def _ensure_v40_tables() -> None:
    from app.models.shop_category import ShopCategory
    from app.models.customer import Customer
    ShopCategory.__table__.create(bind=engine, checkfirst=True)
    Customer.__table__.create(bind=engine, checkfirst=True)

try:
    _ensure_v40_tables()
except Exception as e:  # pragma: no cover
    print(f"[startup] v40 tables ensure skipped: {e}")


# ──────────────────────────────────────────────────────────────────────
# v41 — A customer may have separate B2C and B2B rows under one phone.
# Move the customers unique key from (shop_id, phone) to
# (shop_id, phone, customer_type). Best-effort + idempotent.
# ──────────────────────────────────────────────────────────────────────
def _migrate_customer_unique_key() -> None:
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    if "customers" not in insp.get_table_names():
        return
    with engine.connect() as conn:
        # Drop the old 2-col unique constraint/index if present.
        for stmt in (
            "ALTER TABLE customers DROP CONSTRAINT IF EXISTS uix_customer_shop_phone",
            "DROP INDEX IF EXISTS uix_customer_shop_phone",
        ):
            try:
                conn.execute(text(stmt))
            except Exception:
                pass
        # Add the new 3-col unique index if missing.
        try:
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uix_customer_shop_phone_type "
                "ON customers (shop_id, phone, customer_type)"
            ))
        except Exception:
            pass
        conn.commit()

try:
    _migrate_customer_unique_key()
except Exception as e:  # pragma: no cover
    print(f"[startup] customer unique-key migration skipped: {e}")


# ──────────────────────────────────────────────────────────────────────
# In-place migration: add Debit Note columns to `purchase_returns` and
# create `credit_notes` / `credit_note_items` tables (v25).
#
# Base.metadata.create_all() handles the two new tables automatically
# (they don't exist yet on deployed DBs). The ALTER TABLE block is
# needed for the new nullable columns on the existing purchase_returns
# table — create_all() never alters tables that already exist.
# ──────────────────────────────────────────────────────────────────────
def _migrate_v25() -> None:
    from sqlalchemy import inspect, text

    # ── 1. Ensure credit_notes and credit_note_items tables exist ────────
    # Importing the models registers them with Base.metadata so
    # create_all() picks them up.  This is belt-and-braces for fresh DBs;
    # the explicit create below handles already-deployed DBs where
    # create_all() has already run without these models present.
    from app.models.credit_note import CreditNote, CreditNoteItem  # noqa: F401
    CreditNote.__table__.create(bind=engine, checkfirst=True)
    CreditNoteItem.__table__.create(bind=engine, checkfirst=True)

    new_cols = [
        ("note_number",             "note_number VARCHAR NULL"),
        ("note_date",               "note_date BIGINT NULL"),
        ("note_type",               "note_type VARCHAR(1) NULL"),
        ("original_invoice_id",     "original_invoice_id INTEGER NULL"),
        ("original_invoice_number", "original_invoice_number VARCHAR NULL"),
        ("original_invoice_date",   "original_invoice_date BIGINT NULL"),
        ("place_of_supply",         "place_of_supply VARCHAR NULL"),
        ("supply_type",             "supply_type VARCHAR NULL DEFAULT 'intrastate'"),
        ("cess_amount",             "cess_amount DOUBLE PRECISION NULL DEFAULT 0.0"),
    ]

    # Nullable column names — if any were previously created with NOT NULL
    # (e.g. by an earlier create_all() run before this migration was written),
    # we must explicitly drop that constraint so old clients (which don't send
    # debit-note fields) can still insert rows without crashing.
    nullable_cols = {
        "note_number", "note_date", "note_type",
        "original_invoice_id", "original_invoice_number", "original_invoice_date",
        "place_of_supply", "supply_type", "cess_amount",
    }

    with engine.connect() as conn:
        inspector = inspect(engine)
        existing_col_info = {c["name"]: c for c in inspector.get_columns("purchase_returns")}
        existing = set(existing_col_info.keys())

        for col_name, ddl in new_cols:
            if col_name not in existing:
                conn.execute(text(f"ALTER TABLE purchase_returns ADD COLUMN {ddl}"))
                existing.add(col_name)
            elif col_name in nullable_cols:
                # Column exists — ensure it is nullable. On PostgreSQL the
                # column may have been created with NOT NULL by an earlier
                # create_all() run.  SQLite ignores DROP NOT NULL (no-op).
                try:
                    conn.execute(text(
                        f"ALTER TABLE purchase_returns "
                        f"ALTER COLUMN {col_name} DROP NOT NULL"
                    ))
                except Exception:
                    pass  # SQLite or already nullable — safe to ignore

        conn.commit()


try:
    _migrate_v25()
except Exception as e:  # pragma: no cover
    print(f"[startup] v25 migration skipped: {e}")


def _migrate_v27() -> None:
    from sqlalchemy import inspect, text

    with engine.connect() as conn:
        inspector = inspect(engine)
        if "credit_notes" not in inspector.get_table_names():
            return
            
        cols = {c["name"]: c for c in inspector.get_columns("credit_notes")}
        
        if "note_supply_type" not in cols:
            conn.execute(text("ALTER TABLE credit_notes ADD COLUMN note_supply_type VARCHAR NULL DEFAULT 'Regular'"))
            
        conn.commit()

try:
    _migrate_v27()
except Exception as e:
    print(f"[startup] v27 migration skipped: {e}")


def _migrate_v28() -> None:
    from sqlalchemy import inspect, text

    with engine.connect() as conn:
        inspector = inspect(engine)

        if "shop_products" in inspector.get_table_names():
            cols = {c["name"]: c for c in inspector.get_columns("shop_products")}
            if "supply_classification" not in cols:
                conn.execute(text("ALTER TABLE shop_products ADD COLUMN supply_classification VARCHAR NOT NULL DEFAULT 'TAXABLE'"))

        if "gst_sales_invoice_items" in inspector.get_table_names():
            cols = {c["name"]: c for c in inspector.get_columns("gst_sales_invoice_items")}
            if "supply_classification" not in cols:
                conn.execute(text("ALTER TABLE gst_sales_invoice_items ADD COLUMN supply_classification VARCHAR NOT NULL DEFAULT 'TAXABLE'"))

        if "gst_sales_invoice" in inspector.get_table_names():
            cols = {c["name"]: c for c in inspector.get_columns("gst_sales_invoice")}
            if "document_type" not in cols:
                conn.execute(text("ALTER TABLE gst_sales_invoice ADD COLUMN document_type VARCHAR NULL"))
            if "document_nature" not in cols:
                conn.execute(text("ALTER TABLE gst_sales_invoice ADD COLUMN document_nature VARCHAR NULL"))
            if "document_series" not in cols:
                conn.execute(text("ALTER TABLE gst_sales_invoice ADD COLUMN document_series VARCHAR NULL"))

        conn.commit()

try:
    _migrate_v28()
except Exception as e:
    print(f"[startup] v28 migration skipped: {e}")


def _migrate_v29() -> None:
    from sqlalchemy import inspect, text

    with engine.connect() as conn:
        inspector = inspect(engine)

        if "credit_notes" in inspector.get_table_names():
            cols = {c["name"]: c for c in inspector.get_columns("credit_notes")}
            if "document_type" not in cols:
                conn.execute(text("ALTER TABLE credit_notes ADD COLUMN document_type VARCHAR NULL"))
            if "document_nature" not in cols:
                conn.execute(text("ALTER TABLE credit_notes ADD COLUMN document_nature VARCHAR NULL"))
            if "document_series" not in cols:
                conn.execute(text("ALTER TABLE credit_notes ADD COLUMN document_series VARCHAR NULL"))

        conn.commit()

try:
    _migrate_v29()
except Exception as e:
    print(f"[startup] v29 migration skipped: {e}")


def _migrate_v30() -> None:
    from sqlalchemy import inspect, text

    with engine.connect() as conn:
        inspector = inspect(engine)

        if "purchases" in inspector.get_table_names():
            cols = {c["name"]: c for c in inspector.get_columns("purchases")}
            
            # Columns to add
            cols_to_add = {
                "local_id": "ALTER TABLE purchases ADD COLUMN local_id INTEGER NULL",
                "place_of_supply_code": "ALTER TABLE purchases ADD COLUMN place_of_supply_code VARCHAR NOT NULL DEFAULT ''",
                "reverse_charge": "ALTER TABLE purchases ADD COLUMN reverse_charge VARCHAR NOT NULL DEFAULT 'N'",
                "invoice_type": "ALTER TABLE purchases ADD COLUMN invoice_type VARCHAR NOT NULL DEFAULT 'Regular'",
                "supply_type": "ALTER TABLE purchases ADD COLUMN supply_type VARCHAR NOT NULL DEFAULT 'intrastate'",
                "cess_paid": "ALTER TABLE purchases ADD COLUMN cess_paid DOUBLE PRECISION NOT NULL DEFAULT 0.0",
                "eligibility_for_itc": "ALTER TABLE purchases ADD COLUMN eligibility_for_itc VARCHAR NOT NULL DEFAULT 'Inputs'",
                "availed_itc_integrated_tax": "ALTER TABLE purchases ADD COLUMN availed_itc_integrated_tax DOUBLE PRECISION NOT NULL DEFAULT 0.0",
                "availed_itc_central_tax": "ALTER TABLE purchases ADD COLUMN availed_itc_central_tax DOUBLE PRECISION NOT NULL DEFAULT 0.0",
                "availed_itc_state_tax": "ALTER TABLE purchases ADD COLUMN availed_itc_state_tax DOUBLE PRECISION NOT NULL DEFAULT 0.0",
                "availed_itc_cess": "ALTER TABLE purchases ADD COLUMN availed_itc_cess DOUBLE PRECISION NOT NULL DEFAULT 0.0"
            }
            
            for col, sql in cols_to_add.items():
                if col not in cols:
                    conn.execute(text(sql))
            
            # Create index for local_id
            try:
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_purchases_local_id ON purchases (local_id)"))
            except Exception:
                pass

        conn.commit()

try:
    _migrate_v30()
except Exception as e:
    print(f"[startup] v30 migration skipped: {e}")


def _migrate_v31() -> None:
    from sqlalchemy import inspect, text

    with engine.connect() as conn:
        inspector = inspect(engine)

        if "purchase_items" in inspector.get_table_names():
            cols = {c["name"]: c for c in inspector.get_columns("purchase_items")}
            
            # Columns to add
            cols_to_add = {
                "cess_percentage": "ALTER TABLE purchase_items ADD COLUMN cess_percentage DOUBLE PRECISION NOT NULL DEFAULT 0.0",
                "cess_amount": "ALTER TABLE purchase_items ADD COLUMN cess_amount DOUBLE PRECISION NOT NULL DEFAULT 0.0",
                "eligibility_for_itc": "ALTER TABLE purchase_items ADD COLUMN eligibility_for_itc VARCHAR NOT NULL DEFAULT 'Inputs'",
                "availed_itc_igst": "ALTER TABLE purchase_items ADD COLUMN availed_itc_igst DOUBLE PRECISION NOT NULL DEFAULT 0.0",
                "availed_itc_cgst": "ALTER TABLE purchase_items ADD COLUMN availed_itc_cgst DOUBLE PRECISION NOT NULL DEFAULT 0.0",
                "availed_itc_sgst": "ALTER TABLE purchase_items ADD COLUMN availed_itc_sgst DOUBLE PRECISION NOT NULL DEFAULT 0.0",
                "availed_itc_cess": "ALTER TABLE purchase_items ADD COLUMN availed_itc_cess DOUBLE PRECISION NOT NULL DEFAULT 0.0",
                "hsn_description": "ALTER TABLE purchase_items ADD COLUMN hsn_description VARCHAR NOT NULL DEFAULT ''",
                "official_uqc": "ALTER TABLE purchase_items ADD COLUMN official_uqc VARCHAR NOT NULL DEFAULT ''"
            }
            
            for col, sql in cols_to_add.items():
                if col not in cols:
                    conn.execute(text(sql))

        conn.commit()

try:
    _migrate_v31()
except Exception as e:
    print(f"[startup] v31 migration skipped: {e}")


def _migrate_v32() -> None:
    from sqlalchemy import inspect, text

    with engine.connect() as conn:
        inspector = inspect(engine)

        if "purchase_returns" in inspector.get_table_names():
            cols = {c["name"]: c for c in inspector.get_columns("purchase_returns")}
            
            # Columns to add
            cols_to_add = {
                "document_type": "ALTER TABLE purchase_returns ADD COLUMN document_type VARCHAR NULL",
                "document_nature": "ALTER TABLE purchase_returns ADD COLUMN document_nature VARCHAR NULL",
                "document_series": "ALTER TABLE purchase_returns ADD COLUMN document_series VARCHAR NULL"
            }
            
            for col, sql in cols_to_add.items():
                if col not in cols:
                    conn.execute(text(sql))

        conn.commit()

try:
    _migrate_v32()
except Exception as e:
    print(f"[startup] v32 migration skipped: {e}")


def _migrate_v33() -> None:
    from sqlalchemy import inspect, text

    with engine.connect() as conn:
        inspector = inspect(engine)

        if "purchase_returns" in inspector.get_table_names():
            cols = {c["name"]: c for c in inspector.get_columns("purchase_returns")}
            
            # Columns to add
            cols_to_add = {
                "pre_gst": "ALTER TABLE purchase_returns ADD COLUMN pre_gst VARCHAR NOT NULL DEFAULT 'N'",
                "reason_for_issuing_document": "ALTER TABLE purchase_returns ADD COLUMN reason_for_issuing_document VARCHAR NOT NULL DEFAULT 'Purchase return'",
                "note_refund_voucher_value": "ALTER TABLE purchase_returns ADD COLUMN note_refund_voucher_value DOUBLE PRECISION NOT NULL DEFAULT 0.0",
                "rate": "ALTER TABLE purchase_returns ADD COLUMN rate DOUBLE PRECISION NOT NULL DEFAULT 0.0",
                "eligibility_for_itc": "ALTER TABLE purchase_returns ADD COLUMN eligibility_for_itc VARCHAR NOT NULL DEFAULT 'Inputs'",
                "availed_itc_integrated_tax": "ALTER TABLE purchase_returns ADD COLUMN availed_itc_integrated_tax DOUBLE PRECISION NOT NULL DEFAULT 0.0",
                "availed_itc_central_tax": "ALTER TABLE purchase_returns ADD COLUMN availed_itc_central_tax DOUBLE PRECISION NOT NULL DEFAULT 0.0",
                "availed_itc_state_tax": "ALTER TABLE purchase_returns ADD COLUMN availed_itc_state_tax DOUBLE PRECISION NOT NULL DEFAULT 0.0",
                "availed_itc_cess": "ALTER TABLE purchase_returns ADD COLUMN availed_itc_cess DOUBLE PRECISION NOT NULL DEFAULT 0.0",
                "invoice_type": "ALTER TABLE purchase_returns ADD COLUMN invoice_type VARCHAR NOT NULL DEFAULT 'Regular'",
                "place_of_supply_code": "ALTER TABLE purchase_returns ADD COLUMN place_of_supply_code VARCHAR NOT NULL DEFAULT ''"
            }
            
            for col, sql in cols_to_add.items():
                if col not in cols:
                    conn.execute(text(sql))

        conn.commit()

try:
    _migrate_v33()
except Exception as e:
    print(f"[startup] v33 migration skipped: {e}")


def _migrate_v34() -> None:
    from sqlalchemy import inspect, text

    # Ensure purchase_import_details is created
    from app.models.purchase_import_details import PurchaseImportDetails
    PurchaseImportDetails.__table__.create(bind=engine, checkfirst=True)

    with engine.connect() as conn:
        inspector = inspect(engine)

        if "purchases" in inspector.get_table_names():
            cols = {c["name"]: c for c in inspector.get_columns("purchases")}
            if "purchase_source" not in cols:
                conn.execute(text("ALTER TABLE purchases ADD COLUMN purchase_source VARCHAR NOT NULL DEFAULT 'DOMESTIC'"))

        conn.commit()

try:
    _migrate_v34()
except Exception as e:
    print(f"[startup] v34 migration skipped: {e}")


# ──────────────────────────────────────────────────────────────────────
# One-time cleanup: when _add_gstr_support_columns() added the `active`
# column it used DEFAULT TRUE, which silently stamped every pre-existing
# bill row (old test data, seed data, etc.) as active=TRUE.  Those rows
# also have created_at=NULL because the created_at column didn't exist
# when they were inserted.  They don't belong in any report aggregate.
#
# This migration deactivates them exactly once by flipping active→FALSE
# for any bill that has no created_at.  Idempotent: re-running it is a
# no-op because there will be no more NULL-created_at bills after this.
# ──────────────────────────────────────────────────────────────────────
def _deactivate_stale_bills() -> None:
    from sqlalchemy import text
    with engine.connect() as conn:
        # Deactivate bills with no created_at (pre-date the column).
        r1 = conn.execute(text(
            "UPDATE bills SET active = FALSE "
            "WHERE created_at IS NULL AND active = TRUE"
        ))
        if r1.rowcount:
            print(f"[startup] deactivated {r1.rowcount} stale bill(s) with NULL created_at")

        # NOTE: We deliberately do NOT delete is_cancelled=TRUE bills here.
        # The /bills/create endpoint now returns bill_id=-1 immediately when
        # data.is_cancelled=True, so phantom cancelled bills are never written
        # to the DB in the first place.
        # Deleting cancelled bills at startup would:
        #   1. Erase legitimate user-voided invoices from Bill History (N1
        #      fix shows them with a "Cancelled" badge for audit purposes).
        #   2. Break the credit-note double-count guard in reports: the guard
        #      filters out credit notes where the original bill row is inactive
        #      (active=False). If the row is deleted, the guard never fires,
        #      and the credit note re-enters revenue as a phantom deduction.

        conn.commit()

try:
    _deactivate_stale_bills()
except Exception as e:  # pragma: no cover
    print(f"[startup] stale-bills cleanup skipped: {e}")


# Routers
app.include_router(auth_routes.router)
app.include_router(product_routes.router)
app.include_router(bill_routes.router)
app.include_router(report_routes.router)
app.include_router(shop_routes.router)
app.include_router(billing_settings_routes.router)
app.include_router(security_router)
app.include_router(admin_routes.router)
app.include_router(admin_catalog_router)
app.include_router(analytics_router)
app.include_router(subscription.router)
app.include_router(credit.router)
app.include_router(inventory_routes.router)
app.include_router(sales_routes.router)
app.include_router(profit_routes.router)
app.include_router(gst_routes.router)
app.include_router(global_catalog_router)
app.include_router(purchase_router)
app.include_router(purchase_return_router)
app.include_router(scrap_router)
app.include_router(gst_sales_invoice_router)
app.include_router(purchase_batch_router)
app.include_router(credit_note_router)
from app.routes.purchase_import_details_routes import router as purchase_import_details_router
app.include_router(purchase_import_details_router)
from app.routes.import_service_routes import router as import_service_router
app.include_router(import_service_router)
from app.routes.category_routes import router as category_router
app.include_router(category_router)
from app.routes.customer_routes import router as customer_router
app.include_router(customer_router)
# Units
from app.schemas.product_schema import UnitListResponse

@app.get("/units", response_model=UnitListResponse)
def get_units():
    return {"units": ["piece", "kg", "litre", "gram", "ml", "box"]}


# Root
@app.get("/")
def root():
    return {"message": "POS Backend Running Successfully!"}


scheduler = BackgroundScheduler()
def run_expiry_check():
    db = SessionLocal()
    check_subscriptions(db)
    db.close()


# ⏰ Runs every 24 hours
scheduler.add_job(run_expiry_check, "interval", hours=24)
scheduler.start()


#READY FOR AWS HOSTING
