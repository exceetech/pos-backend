from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base

from app.models import *

from app.routes import auth_routes, profit_routes, sales_routes
from app.routes import product_routes
from app.routes import bill_routes
from app.routes import report_routes
from app.routes import shop_routes
from app.routes import billing_settings_routes
from app.routes.security_routes import router as security_router
from app.routes import admin_routes
from app.routes.analytics_routes import router as analytics_router
from app.routes import subscription_routes as subscription
from app.routes import gst_routes
from app.routes.global_catalog_routes import router as global_catalog_router
from app.routes.purchase_routes import router as purchase_router
from app.routes.purchase_return_routes import router as purchase_return_router
from app.routes.scrap_routes import router as scrap_router
from app.routes.gst_sales_invoice_routes import router as gst_sales_invoice_router
from app.routes.purchase_batch_routes import router as purchase_batch_router



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
        ],
        "gst_sales_invoice": [
            ("invoice_number", "invoice_number VARCHAR NULL DEFAULT ''"),
            ("invoice_date", "invoice_date BIGINT NULL DEFAULT 0"),
            ("reverse_charge", "reverse_charge VARCHAR NOT NULL DEFAULT 'N'"),
            ("gstr_invoice_type", "gstr_invoice_type VARCHAR NOT NULL DEFAULT 'Regular'"),
            ("customer_state_code", "customer_state_code VARCHAR NULL"),
            ("ecommerce_gstin", "ecommerce_gstin VARCHAR NULL"),
            ("ecommerce_operator_name", "ecommerce_operator_name VARCHAR NULL"),
            ("is_cancelled", "is_cancelled BOOLEAN NOT NULL DEFAULT FALSE"),
            ("cancelled_at", "cancelled_at TIMESTAMP NULL"),
        ],
        "gst_sales_invoice_items": [
            ("cess_rate", "cess_rate DOUBLE PRECISION NOT NULL DEFAULT 0.0"),
            ("cess_amount", "cess_amount DOUBLE PRECISION NOT NULL DEFAULT 0.0"),
            ("uqc", "uqc VARCHAR NULL"),
            ("hsn_description", "hsn_description VARCHAR NULL"),
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
        conn.commit()


try:
    _add_gstr_support_columns()
except Exception as e:  # pragma: no cover
    print(f"[startup] GSTR support column migration skipped: {e}")


# Routers
app.include_router(auth_routes.router)
app.include_router(product_routes.router)
app.include_router(bill_routes.router)
app.include_router(report_routes.router)
app.include_router(shop_routes.router)
app.include_router(billing_settings_routes.router)
app.include_router(security_router)
app.include_router(admin_routes.router)
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
