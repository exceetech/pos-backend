"""
Shared query helper for GST sales reporting.

Both the backend GSTR-1/HSN endpoints (app/routes/gst_routes.py) and the
GST summary email (app/services/email_service.py) need the same "active,
in-period sales" data. Prior to this fix each read a *different* table —
the endpoints/email read the legacy `gst_sales_records`, while the in-app
GSTR-1 screen already read the newer `gst_sales_invoice` — and neither
side filtered cancellations consistently. That mismatch is Report 1 issue
S-4, Report 2 issue F-1, and Report 3's Phase C (source-of-truth decision
A2 + repoint step C1). This module is the single place that decision now
lives, so the two readers can't drift apart again.

Source of truth: `gst_sales_invoice` (+ `gst_sales_invoice_items`) — this
is what the in-app GSTR-1 screen already reads, per Report 3 A2.

UPDATE (Report 3, C3 — complete): the legacy `gst_sales_records` table,
its model, and the /gst/sales/sync endpoint have all been removed. This
module is the only GST-sales reader left.
"""
from datetime import datetime
from typing import List, Tuple

from sqlalchemy.orm import Session

from app.models.gst_sales_invoice import GstSalesInvoice, GstSalesInvoiceItem


def to_epoch_ms(dt: datetime) -> int:
    """gst_sales_invoice.invoice_date is stored as epoch-millis (client
    clock at invoice creation time), not a SQL DATETIME — convert here so
    callers can keep working in normal datetimes."""
    return int(dt.timestamp() * 1000)


def get_active_invoice_line_items(
    db: Session, shop_id: int, start: datetime, end: datetime
) -> List[Tuple[GstSalesInvoice, GstSalesInvoiceItem]]:
    """
    Active (non-cancelled) invoice+item rows for a shop within [start, end]
    (inclusive). `end` should already carry 23:59:59 if a full calendar day
    is wanted — this function does no day-rounding of its own.
    """
    start_ms = to_epoch_ms(start)
    end_ms = to_epoch_ms(end)

    return (
        db.query(GstSalesInvoice, GstSalesInvoiceItem)
        .join(
            GstSalesInvoiceItem,
            GstSalesInvoiceItem.gst_invoice_id == GstSalesInvoice.id,
        )
        .filter(
            GstSalesInvoice.shop_id == shop_id,
            GstSalesInvoice.invoice_date >= start_ms,
            GstSalesInvoice.invoice_date <= end_ms,
            GstSalesInvoice.is_cancelled.is_(False),
        )
        .all()
    )


def supply_type_of(item: GstSalesInvoiceItem) -> str:
    """Interstate iff IGST was charged on the line (billing calc audit,
    Report 2 §6: CGST/SGST split intra, full IGST inter — verified)."""
    return "interstate" if (item.igst_amount or 0) > 0 else "intrastate"
