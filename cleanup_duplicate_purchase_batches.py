#!/usr/bin/env python3
"""
cleanup_duplicate_purchase_batches.py — one-shot cleanup of duplicate
purchase_batches rows that were auto-created server-side.

Background
──────────
The Android client is the single source of truth for purchase_batches and
pushes them via POST /purchase-batches/sync. A now-removed block in
/purchases/sync ALSO auto-created a batch per purchase item, producing a
duplicate row per line. The two copies disagreed:

  • client row : batch_code = NULL,  invoice_date = NULL,
                 unit_cost_excluding_tax = net,  gst_percent = cgst+sgst (or igst)
  • server row : batch_code = invoice_number,  invoice_date = <set>,
                 unit_cost_excluding_tax = net,  gst_percent = cgst+sgst+igst (double)

The server-created duplicates are uniquely identifiable: the client NEVER
sends invoice_date (it is always NULL on client-pushed rows), so any row with
`invoice_date IS NOT NULL` is a server-auto-created duplicate. We additionally
require `batch_code = invoice_number` as a second safety check.

Usage (run from the pos-backend directory)
───────────────────────────────────────────
    python cleanup_duplicate_purchase_batches.py            # DRY RUN — shows what would be deleted
    python cleanup_duplicate_purchase_batches.py --apply    # actually delete

Idempotent: once the duplicates are gone, re-running deletes nothing.
This only touches the SERVER database; device-local duplicates are handled
separately on the client.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import text
from app.database import engine

# Rows the client could never have created (it always sends invoice_date = NULL),
# AND whose batch_code echoes the invoice_number — the exact signature of the
# removed server-side auto-create block.
SELECT_DUPES = text(
    """
    SELECT id, shop_id, local_id, product_id, invoice_number,
           batch_code, gst_percent, unit_cost_excluding_tax,
           quantity_purchased, invoice_date
    FROM purchase_batches
    WHERE invoice_date IS NOT NULL
      AND batch_code = invoice_number
    ORDER BY shop_id, product_id, id
    """
)

DELETE_DUPES = text(
    """
    DELETE FROM purchase_batches
    WHERE invoice_date IS NOT NULL
      AND batch_code = invoice_number
    """
)


def main() -> None:
    apply = "--apply" in sys.argv

    with engine.begin() as conn:
        rows = conn.execute(SELECT_DUPES).fetchall()
        total = len(rows)

        print(f"\nFound {total} server-created duplicate purchase_batches row(s).")
        if total == 0:
            print("Nothing to clean up. ✅")
            return

        # Show a small sample so the operator can sanity-check before applying.
        print("\nSample (up to 10):")
        print(f"  {'id':>6} {'shop':>5} {'local':>6} {'prod':>5} "
              f"{'inv#':>8} {'batch_code':>12} {'gst%':>6} {'unit_net':>9} {'qty':>7}")
        for r in rows[:10]:
            print(f"  {r.id:>6} {r.shop_id:>5} {str(r.local_id):>6} {str(r.product_id):>5} "
                  f"{str(r.invoice_number):>8} {str(r.batch_code):>12} {r.gst_percent:>6} "
                  f"{r.unit_cost_excluding_tax:>9} {r.quantity_purchased:>7}")

        if not apply:
            print(f"\nDRY RUN — no rows deleted. Re-run with --apply to delete these {total} row(s).")
            return

        result = conn.execute(DELETE_DUPES)
        print(f"\nDeleted {result.rowcount} duplicate row(s). ✅")


if __name__ == "__main__":
    main()
