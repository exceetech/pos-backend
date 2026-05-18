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

def _to_model(payload, shop_id: int) -> PurchaseReturn:
    """Map a DTO (or DTO-shaped request) onto a fresh ORM row."""
    return PurchaseReturn(
        shop_id           = shop_id,
        shop_product_id   = payload.shop_product_id,
        product_name      = payload.product_name,
        variant_name      = payload.variant_name,
        hsn_code          = payload.hsn_code,
        quantity_returned = payload.quantity_returned,
        taxable_amount    = payload.taxable_amount,
        invoice_value     = payload.invoice_value,
        cgst_percentage   = payload.cgst_percentage,
        sgst_percentage   = payload.sgst_percentage,
        igst_percentage   = payload.igst_percentage,
        cgst_amount       = payload.cgst_amount,
        sgst_amount       = payload.sgst_amount,
        igst_amount       = payload.igst_amount,
        state             = payload.state,
        supplier_gstin    = payload.supplier_gstin,
        supplier_name     = payload.supplier_name,
        is_credit         = 1 if payload.is_credit else 0,
        credit_account_id = payload.credit_account_id,
        created_at        = datetime.utcfromtimestamp(payload.created_at / 1000),
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

            row = _to_model(r, current_shop.id)
            db.add(row)
            db.flush()  # obtain row.id without committing the whole batch
            response.record_id_map[str(r.local_id)] = row.id
            response.success_count += 1
        except Exception as e:
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
