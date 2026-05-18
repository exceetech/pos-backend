"""
Routes for the GST-aware sales-invoice tables.

  • POST /gst-sales              — single insert
  • POST /gst-sales/sync         — bulk insert (offline replay, idempotent on local_id)
  • GET  /gst-sales/{shop_id}    — list, newest first

All writes are scoped to the authenticated shop — the
`shop_id` in the URL is enforced against `current_shop.id`,
never trusted blindly.
"""
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.dependencies import get_current_shop
from app.models.gst_sales_invoice import GstSalesInvoice, GstSalesInvoiceItem
from app.schemas.gst_sales_invoice_schema import (
    CreateGstSalesInvoice,
    GstSalesInvoiceCreate,
    GstSalesInvoiceOut,
    GstSalesSyncBatchRequest,
    GstSalesSyncBatchResponse,
)

router = APIRouter(prefix="/gst-sales", tags=["GST Sales Invoices"])


# --------------------------------------------------------------------
#  Helpers
# --------------------------------------------------------------------

def _epoch_ms_to_dt(ms: int | None) -> datetime:
    if not ms:
        return datetime.utcnow()
    try:
        return datetime.utcfromtimestamp(ms / 1000)
    except (ValueError, OSError):
        return datetime.utcnow()


def _to_invoice(payload: CreateGstSalesInvoice, shop_id: int) -> GstSalesInvoice:
    """Map a DTO onto a fresh ORM row, including the line items."""
    invoice = GstSalesInvoice(
        shop_id        = shop_id,
        bill_id        = payload.bill_id,
        local_id       = payload.local_id,
        invoice_type   = payload.invoice_type,
        gst_scheme     = payload.gst_scheme,
        customer_name  = payload.customer_name,
        business_name  = payload.business_name,
        customer_phone = payload.customer_phone,
        customer_gst   = payload.customer_gst,
        customer_state = payload.customer_state,
        subtotal       = payload.subtotal,
        total_cgst     = payload.total_cgst,
        total_sgst     = payload.total_sgst,
        total_igst     = payload.total_igst,
        total_tax      = payload.total_tax,
        grand_total    = payload.grand_total,
        created_at     = _epoch_ms_to_dt(payload.created_at),
    )
    for item in payload.items:
        invoice.items.append(
            GstSalesInvoiceItem(
                product_id            = item.product_id,
                product_name          = item.product_name,
                variant_name          = item.variant_name,
                hsn_code              = item.hsn_code,
                quantity              = item.quantity,
                selling_price         = item.selling_price,
                taxable_amount        = item.taxable_amount,
                sales_cgst_percentage = item.sales_cgst_percentage,
                sales_sgst_percentage = item.sales_sgst_percentage,
                sales_igst_percentage = item.sales_igst_percentage,
                cgst_amount           = item.cgst_amount,
                sgst_amount           = item.sgst_amount,
                igst_amount           = item.igst_amount,
                net_value             = item.net_value,
            )
        )
    return invoice


# --------------------------------------------------------------------
#  Single insert
# --------------------------------------------------------------------

@router.post("", response_model=GstSalesInvoiceOut)
@router.post("/", response_model=GstSalesInvoiceOut, include_in_schema=False)
def create_gst_sales_invoice(
    payload: GstSalesInvoiceCreate,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop),
):
    if not payload.items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invoice must have at least one line item",
        )

    invoice = _to_invoice(payload, current_shop.id)
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


# --------------------------------------------------------------------
#  Bulk sync (offline replay)
# --------------------------------------------------------------------

@router.post("/sync", response_model=GstSalesSyncBatchResponse)
def sync_gst_sales_invoices(
    payload: GstSalesSyncBatchRequest,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop),
):
    """
    Idempotent bulk upsert.

    For every incoming invoice we look up `(shop_id, local_id)` and:
      • update the existing row in place (cascading items replaced)
      • or insert a fresh one
    Either way the response includes a `local_id → server_id` map
    the client can use to mark its rows synced.
    """
    response = GstSalesSyncBatchResponse()

    for inv_dto in payload.invoices:
        try:
            existing = (
                db.query(GstSalesInvoice)
                  .filter(
                      GstSalesInvoice.shop_id  == current_shop.id,
                      GstSalesInvoice.local_id == inv_dto.local_id,
                  )
                  .first()
            )

            if existing is not None:
                # Replace fields and rewrite line items.
                existing.bill_id        = inv_dto.bill_id
                existing.invoice_type   = inv_dto.invoice_type
                existing.gst_scheme     = inv_dto.gst_scheme
                existing.customer_name  = inv_dto.customer_name
                existing.business_name  = inv_dto.business_name
                existing.customer_phone = inv_dto.customer_phone
                existing.customer_gst   = inv_dto.customer_gst
                existing.customer_state = inv_dto.customer_state
                existing.subtotal       = inv_dto.subtotal
                existing.total_cgst     = inv_dto.total_cgst
                existing.total_sgst     = inv_dto.total_sgst
                existing.total_igst     = inv_dto.total_igst
                existing.total_tax      = inv_dto.total_tax
                existing.grand_total    = inv_dto.grand_total

                # Replace items wholesale — simpler than diffing,
                # and the row is small enough that the cost is fine.
                for item in list(existing.items):
                    db.delete(item)
                for item in inv_dto.items:
                    existing.items.append(
                        GstSalesInvoiceItem(
                            product_id            = item.product_id,
                            product_name          = item.product_name,
                            variant_name          = item.variant_name,
                            hsn_code              = item.hsn_code,
                            quantity              = item.quantity,
                            selling_price         = item.selling_price,
                            taxable_amount        = item.taxable_amount,
                            sales_cgst_percentage = item.sales_cgst_percentage,
                            sales_sgst_percentage = item.sales_sgst_percentage,
                            sales_igst_percentage = item.sales_igst_percentage,
                            cgst_amount           = item.cgst_amount,
                            sgst_amount           = item.sgst_amount,
                            igst_amount           = item.igst_amount,
                            net_value             = item.net_value,
                        )
                    )
                db.flush()
                response.invoice_id_map[str(inv_dto.local_id)] = existing.id
            else:
                row = _to_invoice(inv_dto, current_shop.id)
                db.add(row)
                db.flush()
                response.invoice_id_map[str(inv_dto.local_id)] = row.id

            response.success_count += 1
        except Exception as e:
            response.failed_count += 1
            # Don't bubble — keep replaying the rest of the batch.
            print(f"[gst-sales/sync] local_id={inv_dto.local_id} failed: {e}")

    db.commit()
    response.message = (
        f"{response.success_count}/{len(payload.invoices)} accepted"
    )
    return response


# --------------------------------------------------------------------
#  List
# --------------------------------------------------------------------

@router.get("/{shop_id}", response_model=List[GstSalesInvoiceOut])
def list_gst_sales_invoices(
    shop_id: int,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop),
):
    if shop_id != current_shop.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-shop access denied",
        )

    rows = (
        db.query(GstSalesInvoice)
          .options(selectinload(GstSalesInvoice.items))
          .filter(GstSalesInvoice.shop_id == current_shop.id)
          .order_by(GstSalesInvoice.created_at.desc())
          .all()
    )
    return rows
