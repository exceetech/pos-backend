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
    GstSalesCancelRequest,
    GstSalesCancelResponse,
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
        shop_id                  = shop_id,
        bill_id                  = payload.bill_id,
        local_id                 = payload.local_id,
        invoice_type             = payload.invoice_type,
        gst_scheme               = payload.gst_scheme,
        customer_name            = payload.customer_name,
        business_name            = payload.business_name,
        customer_phone           = payload.customer_phone,
        customer_gst             = payload.customer_gst,
        customer_state           = payload.customer_state,
        subtotal                 = payload.subtotal,
        total_cgst               = payload.total_cgst,
        total_sgst               = payload.total_sgst,
        total_igst               = payload.total_igst,
        total_tax                = payload.total_tax,
        grand_total              = payload.grand_total,
        created_at               = _epoch_ms_to_dt(payload.created_at),
        # ── GSTR-1 invoice-level fields (v23) ──
        invoice_number           = payload.invoice_number,
        invoice_date             = payload.invoice_date or 0,
        reverse_charge           = payload.reverse_charge,
        gstr_invoice_type        = payload.gstr_invoice_type,
        customer_state_code      = payload.customer_state_code,
        ecommerce_gstin          = payload.ecommerce_gstin,
        ecommerce_operator_name  = payload.ecommerce_operator_name,
        is_cancelled             = payload.is_cancelled,
        cancelled_at             = _epoch_ms_to_dt(payload.cancelled_at) if payload.cancelled_at else None,
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
                # ── GSTR-1 item-level fields (v23) ──
                cess_rate             = item.cess_rate,
                cess_amount           = item.cess_amount,
                uqc                   = item.uqc,
                hsn_description       = item.hsn_description,
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
                existing.bill_id                 = inv_dto.bill_id
                existing.invoice_type            = inv_dto.invoice_type
                existing.gst_scheme              = inv_dto.gst_scheme
                existing.customer_name           = inv_dto.customer_name
                existing.business_name           = inv_dto.business_name
                existing.customer_phone          = inv_dto.customer_phone
                existing.customer_gst            = inv_dto.customer_gst
                existing.customer_state          = inv_dto.customer_state
                existing.subtotal                = inv_dto.subtotal
                existing.total_cgst              = inv_dto.total_cgst
                existing.total_sgst              = inv_dto.total_sgst
                existing.total_igst              = inv_dto.total_igst
                existing.total_tax               = inv_dto.total_tax
                existing.grand_total             = inv_dto.grand_total
                # ── GSTR-1 invoice-level fields (v23) ──
                existing.invoice_number          = inv_dto.invoice_number
                existing.invoice_date            = inv_dto.invoice_date or 0
                existing.reverse_charge          = inv_dto.reverse_charge
                existing.gstr_invoice_type       = inv_dto.gstr_invoice_type
                existing.customer_state_code     = inv_dto.customer_state_code
                existing.ecommerce_gstin         = inv_dto.ecommerce_gstin
                existing.ecommerce_operator_name = inv_dto.ecommerce_operator_name
                existing.is_cancelled            = inv_dto.is_cancelled
                if inv_dto.cancelled_at:
                    existing.cancelled_at = _epoch_ms_to_dt(inv_dto.cancelled_at)

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
                            # ── GSTR-1 item-level fields (v23) ──
                            cess_rate             = item.cess_rate,
                            cess_amount           = item.cess_amount,
                            uqc                   = item.uqc,
                            hsn_description       = item.hsn_description,
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
#  Cancel / Void  (POST /gst-sales/cancel)
# --------------------------------------------------------------------

@router.post("/cancel", response_model=GstSalesCancelResponse)
def cancel_gst_sales_invoice(
    payload: GstSalesCancelRequest,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop),
):
    """
    Soft-cancel an invoice.  Locates the row by invoice_number OR server_id
    (whichever the client supplies), sets is_cancelled=True and records
    cancelled_at.  Never deletes a row — the record must remain for audit.
    """
    if not payload.invoice_number and not payload.server_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either invoice_number or server_id is required",
        )

    query = db.query(GstSalesInvoice).filter(
        GstSalesInvoice.shop_id == current_shop.id
    )
    if payload.server_id:
        query = query.filter(GstSalesInvoice.id == payload.server_id)
    else:
        query = query.filter(GstSalesInvoice.invoice_number == payload.invoice_number)

    invoice = query.first()
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found",
        )

    cancelled_dt = (
        _epoch_ms_to_dt(payload.cancelled_at) if payload.cancelled_at else datetime.utcnow()
    )
    invoice.is_cancelled = True
    invoice.cancelled_at = cancelled_dt
    db.commit()
    db.refresh(invoice)

    return GstSalesCancelResponse(success=True, server_id=invoice.id)


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
