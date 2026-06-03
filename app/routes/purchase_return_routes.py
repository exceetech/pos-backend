# routes/purchase_return_routes.py
"""
Purchase-return endpoints.

  • POST /purchase-return                 — single insert
  • POST /purchase-returns/sync           — bulk insert (offline replay)
  • GET  /purchase-return/{shop_id}       — list, newest first

`current_shop` (from dependencies) is the authority on the shop_id
that's actually written to the row — the client may pass an
arbitrary string in `shop_id` (typically the GSTIN), but we never
trust it for the FK; we always store `current_shop.id`.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List

from app.database import get_db
from app.dependencies import get_current_shop
from app.models.purchase_return import PurchaseReturn
from app.schemas.purchase_return_schema import (
    PurchaseReturnCreateRequest,
    PurchaseReturnSyncRequest,
    PurchaseReturnOut,
    PurchaseReturnSyncResponse,
)

router = APIRouter(tags=["Purchase Returns"])


# --------------------------------------------------------------------
#  Helpers
# --------------------------------------------------------------------

def _epoch_ms_to_dt(ms: int | None) -> datetime | None:
    """Safely convert Android epoch millis to a Python datetime."""
    if not ms:
        return None
    try:
        return datetime.utcfromtimestamp(ms / 1000)
    except (ValueError, OSError):
        return None


def validate_gstr2_fields(r) -> str | None:
    """Validate GSTR-2 fields if note_type is 'D'. Returns error message or None."""
    if getattr(r, "note_type", None) != "D":
        return None

    pre_gst = getattr(r, "pre_gst", "N")
    if pre_gst not in ["Y", "N"]:
        return "pre_gst must be Y or N"

    if not getattr(r, "document_type", None):
        return "document_type is required"

    if not getattr(r, "reason_for_issuing_document", None):
        return "reason_for_issuing_document is required"

    note_refund_voucher_value = getattr(r, "note_refund_voucher_value", 0.0)
    if note_refund_voucher_value <= 0:
        return "note_refund_voucher_value must be > 0"

    taxable_amount = getattr(r, "taxable_amount", 0.0)
    if note_refund_voucher_value < (taxable_amount - 0.02):
        return f"note_refund_voucher_value ({note_refund_voucher_value}) must stay >= taxable_amount ({taxable_amount})"

    rate = getattr(r, "rate", 0.0)
    if rate < 0:
        return "rate must be >= 0"

    eligibility_for_itc = getattr(r, "eligibility_for_itc", None)
    if not eligibility_for_itc:
        return "eligibility_for_itc is required"

    availed_itc_integrated_tax = getattr(r, "availed_itc_integrated_tax", 0.0)
    availed_itc_central_tax = getattr(r, "availed_itc_central_tax", 0.0)
    availed_itc_state_tax = getattr(r, "availed_itc_state_tax", 0.0)
    availed_itc_cess = getattr(r, "availed_itc_cess", 0.0)

    if availed_itc_integrated_tax < 0 or availed_itc_central_tax < 0 or availed_itc_state_tax < 0 or availed_itc_cess < 0:
        return "availed ITC values must be >= 0"

    if eligibility_for_itc in ["Ineligible", "None"]:
        if (
            availed_itc_integrated_tax != 0.0 or
            availed_itc_central_tax != 0.0 or
            availed_itc_state_tax != 0.0 or
            availed_itc_cess != 0.0
        ):
            return "If eligibility_for_itc is Ineligible/None, availed ITC values must be 0"
    else:
        igst_amount = getattr(r, "igst_amount", 0.0)
        cgst_amount = getattr(r, "cgst_amount", 0.0)
        sgst_amount = getattr(r, "sgst_amount", 0.0)
        cess_amount = getattr(r, "cess_amount", 0.0)

        if availed_itc_integrated_tax > (igst_amount + 0.02):
            return f"availed_itc_integrated_tax ({availed_itc_integrated_tax}) cannot exceed igst_amount ({igst_amount})"
        if availed_itc_central_tax > (cgst_amount + 0.02):
            return f"availed_itc_central_tax ({availed_itc_central_tax}) cannot exceed cgst_amount ({cgst_amount})"
        if availed_itc_state_tax > (sgst_amount + 0.02):
            return f"availed_itc_state_tax ({availed_itc_state_tax}) cannot exceed sgst_amount ({sgst_amount})"
        if availed_itc_cess > (cess_amount + 0.02):
            return f"availed_itc_cess ({availed_itc_cess}) cannot exceed cess_amount ({cess_amount})"

    if not getattr(r, "invoice_type", None):
        return "invoice_type is required"

    if not getattr(r, "place_of_supply_code", None):
        return "place_of_supply_code is required"

    return None


def _to_model(payload, shop_id: int) -> PurchaseReturn:
    """Map a DTO (or DTO-shaped request) onto a fresh ORM row."""
    return PurchaseReturn(
        shop_id                 = shop_id,
        shop_product_id         = payload.shop_product_id,
        product_name            = payload.product_name,
        variant_name            = payload.variant_name,
        hsn_code                = payload.hsn_code,
        quantity_returned       = payload.quantity_returned,
        taxable_amount          = payload.taxable_amount,
        invoice_value           = payload.invoice_value,
        cgst_percentage         = payload.cgst_percentage,
        sgst_percentage         = payload.sgst_percentage,
        igst_percentage         = payload.igst_percentage,
        cgst_amount             = payload.cgst_amount,
        sgst_amount             = payload.sgst_amount,
        igst_amount             = payload.igst_amount,
        state                   = payload.state,
        supplier_gstin          = payload.supplier_gstin,
        supplier_name           = payload.supplier_name,
        is_credit               = 1 if payload.is_credit else 0,
        credit_account_id       = payload.credit_account_id,
        created_at              = datetime.utcfromtimestamp(payload.created_at / 1000),
        # ── Debit/Credit Note fields (v25+) ──────────────────────────────
        note_number             = getattr(payload, "note_number", None),
        note_date               = getattr(payload, "note_date", None),
        note_type               = getattr(payload, "note_type", None),
        original_invoice_id     = getattr(payload, "original_invoice_id", None),
        original_invoice_number = getattr(payload, "original_invoice_number", None),
        original_invoice_date   = getattr(payload, "original_invoice_date", None),
        place_of_supply         = getattr(payload, "place_of_supply", None),
        supply_type             = getattr(payload, "supply_type", "intrastate"),
        cess_amount             = getattr(payload, "cess_amount", 0.0),
        tax_amount              = getattr(payload, "tax_amount", 0.0),
        total_amount            = getattr(payload, "total_amount", 0.0),
        document_type           = getattr(payload, "document_type", None) or ("Debit Note" if getattr(payload, "note_type", "D") == "D" else "Credit Note"),
        document_nature         = getattr(payload, "document_nature", None) or ("Debit Note" if getattr(payload, "note_type", "D") == "D" else "Credit Note"),
        document_series         = getattr(payload, "document_series", None) or (
            getattr(payload, "note_number", "").split("-")[0] 
            if getattr(payload, "note_number", "") and "-" in getattr(payload, "note_number", "")
            else ("DN" if getattr(payload, "note_type", "D") == "D" else "CN")
        ),
        pre_gst                 = getattr(payload, "pre_gst", "N"),
        reason_for_issuing_document = getattr(payload, "reason_for_issuing_document", "Purchase return"),
        note_refund_voucher_value = getattr(payload, "note_refund_voucher_value", 0.0),
        rate                    = getattr(payload, "rate", 0.0),
        eligibility_for_itc     = getattr(payload, "eligibility_for_itc", "Inputs"),
        availed_itc_integrated_tax = getattr(payload, "availed_itc_integrated_tax", 0.0),
        availed_itc_central_tax  = getattr(payload, "availed_itc_central_tax", 0.0),
        availed_itc_state_tax    = getattr(payload, "availed_itc_state_tax", 0.0),
        availed_itc_cess         = getattr(payload, "availed_itc_cess", 0.0),
        invoice_type            = getattr(payload, "invoice_type", "Regular"),
        place_of_supply_code    = getattr(payload, "place_of_supply_code", ""),
    )


# --------------------------------------------------------------------
#  Single insert
# --------------------------------------------------------------------

@router.post("/purchase-return", response_model=PurchaseReturnOut)
def create_purchase_return(
    payload: PurchaseReturnCreateRequest,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop),
):
    if payload.quantity_returned <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="quantity_returned must be > 0",
        )
    if payload.note_type and payload.note_type not in ["C", "D"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="note_type must be C or D",
        )

    err = validate_gstr2_fields(payload)
    if err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err,
        )

    row = _to_model(payload, current_shop.id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# --------------------------------------------------------------------
#  Bulk sync (offline replay)
# --------------------------------------------------------------------

@router.post("/purchase-returns/sync", response_model=PurchaseReturnSyncResponse)
def sync_purchase_returns(
    payload: PurchaseReturnSyncRequest,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop),
):
    response = PurchaseReturnSyncResponse()

    for r in payload.records:
        try:
            if r.quantity_returned <= 0:
                response.failed.append({
                    "local_id": r.local_id,
                    "reason": "quantity_returned must be > 0",
                })
                continue
            if r.note_type and r.note_type not in ["C", "D"]:
                response.failed.append({
                    "local_id": r.local_id,
                    "reason": "note_type must be C or D",
                })
                continue

            err = validate_gstr2_fields(r)
            if err:
                response.failed.append({
                    "local_id": r.local_id,
                    "reason": err,
                })
                continue

            row = _to_model(r, current_shop.id)
            db.add(row)
            db.flush()  # obtain row.id without committing the whole batch
            response.record_id_map[str(r.local_id)] = row.id
            response.success_count += 1
        except Exception as e:
            # flush() raised (e.g. NOT NULL violation) — the session's
            # transaction is in a rolled-back state.  Explicit rollback lets
            # the loop continue for remaining records instead of crashing the
            # whole batch with PendingRollbackError on db.commit().
            db.rollback()
            response.failed.append({"local_id": r.local_id, "reason": str(e)})

    db.commit()
    response.message = f"{response.success_count}/{len(payload.records)} accepted"
    return response


# --------------------------------------------------------------------
#  List
# --------------------------------------------------------------------

@router.get("/purchase-return/{shop_id}", response_model=List[PurchaseReturnOut])
def list_purchase_returns(
    shop_id: int,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop),
):
    # Guard: a shop can only read its own returns. The path id
    # exists for cleanliness; we still enforce against the
    # authenticated shop.
    if shop_id != current_shop.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-shop access denied",
        )

    rows = (
        db.query(PurchaseReturn)
          .filter(PurchaseReturn.shop_id == current_shop.id)
          .order_by(PurchaseReturn.created_at.desc())
          .all()
    )
    return rows
