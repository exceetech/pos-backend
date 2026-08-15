"""
Compares every SQLAlchemy model's expected columns against what actually
exists in the connected database, and reports any mismatch.

This exists because of a real incident (2026-08-15): StoreGstProfile.address
was defined on the model but never had a matching Alembic migration. It
went undetected for a long time because every database this app had ever
run against was originally bootstrapped (at least in part) via
Base.metadata.create_all(), which silently creates whatever columns the
model currently defines. It only surfaced once create_all() was removed
and a database was built strictly from `alembic upgrade head` — this
script exists to catch the next one on purpose, rather than by accident
in production logs.

Usage:
    export DATABASE_URL=postgresql://...   # point this at whichever DB
                                            # you want to check (local,
                                            # or a Cloud SQL instance via
                                            # the Cloud SQL Auth Proxy)
    python3 scripts/check_schema_drift.py

Exits non-zero if any drift is found, so it can also be wired into CI
later if a pipeline gets built.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, inspect

from app.database import Base
from app.models import *  # noqa: F401,F403 — imports every model so Base.metadata is fully populated


def main() -> int:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL not set — point this at the database you want to check.")
        return 1

    engine = create_engine(database_url)
    inspector = inspect(engine)
    db_tables = set(inspector.get_table_names())

    drift_found = False

    for table_name, table in Base.metadata.tables.items():
        if table_name not in db_tables:
            print(f"[MISSING TABLE] '{table_name}' is defined in models but does not exist in the database at all.")
            drift_found = True
            continue

        db_columns = {c["name"] for c in inspector.get_columns(table_name)}
        model_columns = {c.name for c in table.columns}

        missing_in_db = model_columns - db_columns
        extra_in_db = db_columns - model_columns

        if missing_in_db:
            print(f"[MISSING COLUMN] {table_name}: model defines {sorted(missing_in_db)} but the database does not have {'them' if len(missing_in_db) > 1 else 'it'}.")
            drift_found = True

        if extra_in_db:
            # Not necessarily a bug (could be an old column a migration
            # intentionally left in place rather than dropping), but
            # worth surfacing for awareness.
            print(f"[EXTRA COLUMN]   {table_name}: database has {sorted(extra_in_db)} that the model doesn't define.")

    if not drift_found:
        print("No missing tables or columns found — models and database schema agree.")
        return 0

    print("\nDrift found above. For each [MISSING COLUMN]/[MISSING TABLE], write a migration (see migrations/versions/0048_add_store_gst_profile_address.py for the pattern) before this matters in production.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
