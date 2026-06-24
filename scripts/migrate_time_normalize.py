#!/usr/bin/env python3
"""
Phase 5 — one-time historical time normalization (PostgreSQL).

WHY
---
Before the time-fix, the same database held event timestamps written under
three conventions:

  • naive UTC        — utcnow() defaults + utcfromtimestamp() ingestion
  • naive server-local — datetime.now() + fromtimestamp() ingestion
  • timestamptz       — func.now() (credits / customers)

The new convention is: every EVENT time is a NAIVE wall-clock value in the shop
timezone (APP_TIMEZONE). New rows already follow it. This script rewrites OLD
rows to match so reports computed across old+new data line up.

It does NOT touch Bucket-B columns (updated_at sync cursors, subscription
expiry, JWT/OTP) — those stay UTC by design.

SAFETY
------
  • DRY-RUN BY DEFAULT. Prints data type, row count, min/max and sample rows for
    every target column, plus the value each shift WOULD produce. Writes nothing
    until you pass --apply.
  • IDEMPOTENT. Every operation records a key in `time_migration_applied`; a
    second run skips anything already done, so it can't double-shift.
  • TRANSACTIONAL. --apply runs inside one transaction and rolls back on error.
  • Take a database backup first anyway.

The production server's historical timezone is unknown, so:
  • Group A (naive UTC) is ALWAYS shifted by +offset (UTC → shop wall clock).
  • Group B (naive server-local) is shifted ONLY if you pass --server-was utc.
    If the server already ran in the shop timezone, those values are correct.
  • Group C (timestamptz) is converted with `AT TIME ZONE <shop_tz>`, which is
    correct regardless of the old server timezone.

USAGE
-----
  # 1) Look first (no writes):
  python scripts/migrate_time_normalize.py --dry-run
  # 2) Apply (server historically ran in shop TZ — the common case):
  python scripts/migrate_time_normalize.py --apply --yes
  # 3) Apply when the old server ran in UTC:
  python scripts/migrate_time_normalize.py --apply --server-was utc --yes

Reads DATABASE_URL from the env (same as the app) unless --database-url given.
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, text


# ── Target columns, grouped by their PRE-FIX storage convention ───────────────
# (table, column). Edit these lists if your schema differs.

# Group A — stored as NAIVE UTC (utcnow / utcfromtimestamp). Always +offset.
UTC_COLUMNS = [
    ("inventory_logs",      "created_at"),
    ("purchases",           "created_at"),
    ("purchases",           "invoice_date"),
    ("purchase_batches",    "created_at"),
    ("purchase_returns",    "created_at"),
    ("scrap_entries",       "created_at"),
    ("credit_notes",        "created_at"),
    ("gst_sales_invoice",   "created_at"),
    ("gst_sales_invoice",   "cancelled_at"),
    ("gst_sales_records",   "created_at"),
    ("gst_purchase_records","created_at"),
    ("store_gst_profile",   "created_at"),
    ("shops",               "created_at"),
    ("bills",               "cancelled_at"),   # was utcnow() before the fix
]

# Group B — stored as NAIVE SERVER-LOCAL (datetime.now / fromtimestamp).
# Correct already IF the server ran in the shop TZ; shift only with --server-was utc.
SERVER_LOCAL_COLUMNS = [
    ("sale_items",              "created_at"),
    ("purchase_import_details", "created_at"),
    ("purchase_import_details", "bill_of_entry_date"),
    ("import_services",         "invoice_date"),
]

# Group C — TIMESTAMPTZ via func.now(). Convert to naive shop wall clock.
TZ_COLUMNS = [
    ("credit_accounts",     "created_at"),
    ("credit_transactions", "created_at"),
    ("customers",           "created_at"),
]

# Columns explicitly LEFT ALONE (documented, not migrated):
#   bills.created_at, bill_items.created_at      -> already shop-local (local_now)
#   *.updated_at                                 -> Bucket B (UTC cursor)
#   subscriptions.expiry_date / start_date       -> Bucket B (UTC)

MARKER_TABLE = "time_migration_applied"


def shop_offset_minutes(shop_tz: str) -> int:
    """UTC→shop offset in minutes (e.g. +330 for IST). India has no DST."""
    now = datetime.now(timezone.utc)
    off = ZoneInfo(shop_tz).utcoffset(now)
    return int(off.total_seconds() // 60)


def ensure_marker(conn):
    conn.execute(text(
        f"CREATE TABLE IF NOT EXISTS {MARKER_TABLE} "
        f"(key text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
    ))


def already_done(conn, key: str) -> bool:
    r = conn.execute(text(f"SELECT 1 FROM {MARKER_TABLE} WHERE key = :k"), {"k": key})
    return r.first() is not None


def mark_done(conn, key: str):
    conn.execute(text(f"INSERT INTO {MARKER_TABLE}(key) VALUES (:k) "
                      f"ON CONFLICT (key) DO NOTHING"), {"k": key})


def table_exists(conn, table: str) -> bool:
    r = conn.execute(text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = current_schema() AND table_name = :t"
    ), {"t": table})
    return r.first() is not None


def column_type(conn, table: str, column: str):
    r = conn.execute(text(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = :t AND column_name = :c"
    ), {"t": table, "c": column}).first()
    return r[0] if r else None


def preview(conn, table: str, column: str, offset: int, kind: str):
    dtype = column_type(conn, table, column)
    if dtype is None:
        print(f"  [skip] {table}.{column}: column not found")
        return
    cnt = conn.execute(text(
        f"SELECT count(*) FROM {table} WHERE {column} IS NOT NULL")).scalar()
    mn, mx = conn.execute(text(
        f"SELECT min({column}), max({column}) FROM {table}")).first()
    print(f"  {table}.{column}  type={dtype}  non-null={cnt}  min={mn}  max={mx}  [{kind}]")
    rows = conn.execute(text(
        f"SELECT {column} FROM {table} WHERE {column} IS NOT NULL "
        f"ORDER BY {column} DESC LIMIT 3")).fetchall()
    for (val,) in rows:
        if kind == "tz-convert" and val is not None:
            # show what AT TIME ZONE would produce
            shown = conn.execute(text(
                "SELECT (:v AT TIME ZONE :tz)"), {"v": val, "tz": SHOP_TZ}).scalar()
            print(f"       sample {val}  ->  {shown}  (AT TIME ZONE {SHOP_TZ})")
        elif val is not None:
            print(f"       sample {val}  ->  {val} + {offset}min")


def apply_shift(conn, table, column, offset, key):
    if already_done(conn, key):
        print(f"  [done already] {key}")
        return 0
    res = conn.execute(text(
        f"UPDATE {table} SET {column} = {column} + (:off * interval '1 minute') "
        f"WHERE {column} IS NOT NULL"), {"off": offset})
    mark_done(conn, key)
    print(f"  [shifted +{offset}min] {table}.{column}  rows={res.rowcount}")
    return res.rowcount


def apply_tz_convert(conn, table, column, key):
    if already_done(conn, key):
        print(f"  [done already] {key}")
        return
    dtype = column_type(conn, table, column)
    if dtype is None:
        print(f"  [skip] {table}.{column}: not found")
        return
    if "with time zone" in (dtype or ""):
        # timestamptz -> naive shop wall clock + change type
        conn.execute(text(
            f"ALTER TABLE {table} ALTER COLUMN {column} TYPE timestamp without time zone "
            f"USING ({column} AT TIME ZONE '{SHOP_TZ}')"))
        print(f"  [tz-converted + retyped] {table}.{column}  (AT TIME ZONE {SHOP_TZ})")
    else:
        # already naive — leave the value, just record so we don't revisit
        print(f"  [already naive, no value change] {table}.{column}  type={dtype}")
    mark_done(conn, key)


SHOP_TZ = "Asia/Kolkata"  # set from args at runtime


def main():
    global SHOP_TZ
    ap = argparse.ArgumentParser(description="Phase 5 historical time normalization (Postgres).")
    ap.add_argument("--database-url", default=os.getenv("DATABASE_URL"),
                    help="Postgres URL (default: $DATABASE_URL)")
    ap.add_argument("--shop-tz", default=os.getenv("APP_TIMEZONE", "Asia/Kolkata"))
    ap.add_argument("--shift-minutes", type=int, default=None,
                    help="Override the UTC→shop offset (default: derived from --shop-tz)")
    ap.add_argument("--server-was", choices=["shop", "utc"], default="shop",
                    help="Historical server timezone. 'utc' also shifts Group-B columns.")
    ap.add_argument("--apply", action="store_true", help="Actually write (default: dry-run)")
    ap.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")
    args = ap.parse_args()

    if not args.database_url:
        sys.exit("ERROR: no DATABASE_URL (pass --database-url or set the env var).")

    SHOP_TZ = args.shop_tz
    offset = args.shift_minutes if args.shift_minutes is not None else shop_offset_minutes(SHOP_TZ)
    dry = not args.apply

    print("=" * 70)
    print(f"Phase 5 time normalization | shop_tz={SHOP_TZ} offset=+{offset}min "
          f"server_was={args.server_was} mode={'DRY-RUN' if dry else 'APPLY'}")
    print("=" * 70)

    engine = create_engine(args.database_url)
    with engine.connect() as conn:
        trans = conn.begin()               # explicit tx: we control commit/rollback
        try:
            ensure_marker(conn)

            print("\n[Group A] naive-UTC columns  (always +offset):")
            for t, c in UTC_COLUMNS:
                if not table_exists(conn, t):
                    print(f"  [skip] {t}: table not found"); continue
                if dry: preview(conn, t, c, offset, "shift")
                else:   apply_shift(conn, t, c, offset, f"shiftA:{t}.{c}")

            print(f"\n[Group B] naive server-local columns  "
                  f"({'+offset' if args.server_was=='utc' else 'LEFT (server ran in shop TZ)'}):")
            for t, c in SERVER_LOCAL_COLUMNS:
                if not table_exists(conn, t):
                    print(f"  [skip] {t}: table not found"); continue
                if dry:
                    preview(conn, t, c, offset if args.server_was == "utc" else 0,
                            "shift" if args.server_was == "utc" else "leave")
                elif args.server_was == "utc":
                    apply_shift(conn, t, c, offset, f"shiftB:{t}.{c}")
                else:
                    print(f"  [left] {t}.{c}")

            print("\n[Group C] timestamptz columns  (AT TIME ZONE -> naive shop wall clock):")
            for t, c in TZ_COLUMNS:
                if not table_exists(conn, t):
                    print(f"  [skip] {t}: table not found"); continue
                if dry: preview(conn, t, c, 0, "tz-convert")
                else:   apply_tz_convert(conn, t, c, f"tz:{t}.{c}")

            if dry:
                trans.rollback()
                print("\nDRY-RUN: rolled back, nothing written. Re-run with --apply to commit.")
            else:
                if not args.yes:
                    ans = input("\nCommit these changes? [y/N] ").strip().lower()
                    if ans != "y":
                        trans.rollback()
                        sys.exit("Aborted; rolled back.")
                trans.commit()
                print("\nAPPLIED and committed.")
        except Exception:
            trans.rollback()
            raise

    print("\nDone.")


if __name__ == "__main__":
    main()
