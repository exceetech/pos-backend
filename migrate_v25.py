#!/usr/bin/env python3
"""
migrate_v25.py — one-shot migration for the v25 schema changes.

Run from the pos-backend directory:

    python migrate_v25.py

What it does
────────────
1. Creates `credit_notes` and `credit_note_items` tables if they don't
   already exist.
2. Adds 9 new Debit Note columns to the existing `purchase_returns` table
   (all nullable / defaulted, so existing rows stay valid).

All operations are idempotent — safe to run more than once.

The same migration also runs automatically at FastAPI startup via
`_migrate_v25()` in `app/main.py`, so this standalone script is only
needed if you want to apply the schema before (re-)deploying the app.
"""

import sys
import os

# Make sure the app package is importable from the root directory
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import inspect, text
from app.database import engine, Base

# Import all models so Base.metadata knows about them
import app.models  # noqa: F401  — triggers __init__.py side-effects


def run() -> None:
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())

    # ── 1. Create credit_notes + credit_note_items ───────────────────────
    print("[migrate_v25] Ensuring credit_notes table …", end=" ")
    from app.models.credit_note import CreditNote, CreditNoteItem
    CreditNote.__table__.create(bind=engine, checkfirst=True)
    CreditNoteItem.__table__.create(bind=engine, checkfirst=True)
    print("done.")

    # ── 2. Add debit-note columns to purchase_returns ────────────────────
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
        ("tax_amount",              "tax_amount DOUBLE PRECISION NULL DEFAULT 0.0"),
        ("total_amount",            "total_amount DOUBLE PRECISION NULL DEFAULT 0.0"),
    ]

    # Columns that must be nullable — if any were created with NOT NULL by an
    # earlier create_all() run we explicitly drop that constraint here.
    nullable_cols = {
        "note_number", "note_date", "note_type",
        "original_invoice_id", "original_invoice_number", "original_invoice_date",
        "place_of_supply", "supply_type", "cess_amount",
        "tax_amount", "total_amount",
    }

    if "purchase_returns" not in existing_tables:
        print("[migrate_v25] purchase_returns does not exist yet — skipping ALTER.")
    else:
        with engine.connect() as conn:
            current_cols = {c["name"] for c in insp.get_columns("purchase_returns")}
            added = []
            fixed_nullability = []

            for col_name, ddl in new_cols:
                if col_name not in current_cols:
                    conn.execute(text(f"ALTER TABLE purchase_returns ADD COLUMN {ddl}"))
                    added.append(col_name)
                elif col_name in nullable_cols:
                    # Column already exists — ensure it is actually nullable.
                    # PostgreSQL may have created it as NOT NULL via create_all().
                    try:
                        conn.execute(text(
                            f"ALTER TABLE purchase_returns "
                            f"ALTER COLUMN {col_name} DROP NOT NULL"
                        ))
                        fixed_nullability.append(col_name)
                    except Exception:
                        pass  # already nullable or SQLite — safe to ignore

            conn.commit()
            if added:
                print(f"[migrate_v25] Added columns to purchase_returns: {added}")
            if fixed_nullability:
                print(f"[migrate_v25] Dropped NOT NULL from: {fixed_nullability}")
            if not added and not fixed_nullability:
                print("[migrate_v25] purchase_returns already up to date.")

    # ── 3. Add index on note_number if not present ───────────────────────
    with engine.connect() as conn:
        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_purchase_returns_note_number "
                "ON purchase_returns (note_number)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_purchase_returns_original_invoice_id "
                "ON purchase_returns (original_invoice_id)"
            ))
            conn.commit()
            print("[migrate_v25] Indexes ensured.")
        except Exception as e:
            print(f"[migrate_v25] Index creation skipped (may already exist): {e}")

    print("[migrate_v25] Migration complete.")


if __name__ == "__main__":
    run()
