# routes/scrap_routes.py
"""
Scrap endpoints — same shape as purchase_return_routes but for
the scrap_entries table.

  • POST /scrap                  — single insert
  • POST /scrap/sync             — bulk insert (offline replay)
  • GET  /scrap/{shop_id}        — list, newest first
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List

from app.database import get_db
from app.dependencies import get_current_shop
from app.models.scrap import Scrap
from app.schemas.scrap_schema import (
    ScrapCreateRequest,
    ScrapSyncRequest,
    ScrapOut,
    ScrapSyncResponse,
)

router = APIRouter(tags=["Scrap"])


def _to_model(payload, shop_id: int) -> Scrap:
    return Scrap(
        shop_id          = shop_id,
        shop_product_id  = payload.shop_product_id,
        product_name     = payload.product_name,
        variant_name     = payload.variant_name,
        hsn_code         = payload.hsn_code,
        quantity         = payload.quantity,
        taxable_amount   = payload.taxable_amount,
        invoice_value    = payload.invoice_value,
        cgst_percentage  = payload.cgst_percentage,
        sgst_percentage  = payload.sgst_percentage,
        igst_percentage  = payload.igst_percentage,
        cgst_amount      = payload.cgst_amount,
        sgst_amount      = payload.sgst_amount,
        igst_amount      = payload.igst_amount,
        state            = payload.state,
        reason           = payload.reason,
        created_at       = datetime.utcfromtimestamp(payload.created_at / 1000),
    )


@router.post("/scrap", response_model=ScrapOut)
def create_scrap(
    payload: ScrapCreateRequest,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop),
):
    if payload.quantity <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="quantity must be > 0",
        )

    row = _to_model(payload, current_shop.id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.post("/scrap/sync", response_model=ScrapSyncResponse)
def sync_scrap(
    payload: ScrapSyncRequest,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop),
):
    response = ScrapSyncResponse()

    for r in payload.records:
        try:
            if r.quantity <= 0:
                response.failed.append({
                    "local_id": r.local_id,
                    "reason": "quantity must be > 0",
                })
                continue

            row = _to_model(r, current_shop.id)
            db.add(row)
            db.flush()
            response.record_id_map[str(r.local_id)] = row.id
            response.success_count += 1
        except Exception as e:
            response.failed.append({"local_id": r.local_id, "reason": str(e)})

    db.commit()
    response.message = f"{response.success_count}/{len(payload.records)} accepted"
    return response


@router.get("/scrap/{shop_id}", response_model=List[ScrapOut])
def list_scrap(
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
        db.query(Scrap)
          .filter(Scrap.shop_id == current_shop.id)
          .order_by(Scrap.created_at.desc())
          .all()
    )
    return rows
