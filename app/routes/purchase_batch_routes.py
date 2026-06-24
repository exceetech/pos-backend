"""
Routes for hybrid-inventory purchase_batches.

  • POST /purchase-batches/sync      — idempotent bulk upsert
  • GET  /purchase-batches/{shop_id} — list, newest first
"""
from datetime import datetime
from app.util.time_utils import epoch_ms_to_local, local_now
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_shop
from app.models.purchase_batch import PurchaseBatch
from app.schemas.purchase_batch_schema import (
    PurchaseBatchSyncRequest,
    PurchaseBatchSyncResponse,
)

router = APIRouter(prefix="/purchase-batches", tags=["Purchase Batches"])


def _to_dt(ms):
    if not ms:
        return None
    try:
        return epoch_ms_to_local(ms)
    except (ValueError, OSError):
        return None


@router.post("/sync", response_model=PurchaseBatchSyncResponse)
def sync_purchase_batches(
    payload: PurchaseBatchSyncRequest,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop),
):
    response = PurchaseBatchSyncResponse()

    for b in payload.batches:
        try:
            existing = (
                db.query(PurchaseBatch)
                  .filter(
                      PurchaseBatch.shop_id  == current_shop.id,
                      PurchaseBatch.local_id == b.local_id,
                  )
                  .first()
            )

            fields = dict(
                product_id              = b.product_id,
                purchase_invoice_id     = b.purchase_invoice_id,
                supplier_name           = b.supplier_name,
                supplier_gstin          = b.supplier_gstin,
                invoice_number          = b.invoice_number,
                batch_code              = b.batch_code,
                quantity_purchased      = b.quantity_purchased,
                quantity_remaining      = b.quantity_remaining,
                unit_cost_excluding_tax = b.unit_cost_excluding_tax,
                gst_percent             = b.gst_percent,
                cgst_percent            = b.cgst_percent,
                sgst_percent            = b.sgst_percent,
                igst_percent            = b.igst_percent,
                invoice_value           = b.invoice_value,
                taxable_value           = b.taxable_value,
                invoice_date            = _to_dt(b.invoice_date),
            )

            if existing is not None:
                for k, v in fields.items():
                    setattr(existing, k, v)
                row = existing
            else:
                row = PurchaseBatch(
                    shop_id = current_shop.id,
                    local_id = b.local_id,
                    created_at = _to_dt(b.created_at) or local_now(),
                    **fields,
                )
                db.add(row)

            db.flush()
            response.batch_id_map[str(b.local_id)] = row.id
            response.success_count += 1
        except Exception as e:
            print(f"[purchase-batches/sync] local_id={b.local_id} failed: {e}")

    db.commit()
    response.message = f"{response.success_count}/{len(payload.batches)} accepted"
    return response


@router.get("/{shop_id}")
def list_purchase_batches(
    shop_id: int,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop),
):
    if shop_id != current_shop.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-shop access denied")
    rows = (
        db.query(PurchaseBatch)
          .filter(PurchaseBatch.shop_id == current_shop.id)
          .order_by(PurchaseBatch.created_at.desc())
          .all()
    )
    return [
        {
            "id": r.id,
            "local_id": r.local_id,
            "product_id": r.product_id,
            "purchase_invoice_id": r.purchase_invoice_id,
            "supplier_name": r.supplier_name,
            "supplier_gstin": r.supplier_gstin,
            "invoice_number": r.invoice_number,
            "batch_code": r.batch_code,
            "quantity_purchased": r.quantity_purchased,
            "quantity_remaining": r.quantity_remaining,
            "unit_cost_excluding_tax": r.unit_cost_excluding_tax,
            "gst_percent": r.gst_percent,
            "cgst_percent": r.cgst_percent,
            "sgst_percent": r.sgst_percent,
            "igst_percent": r.igst_percent,
            "invoice_value": r.invoice_value,
            "taxable_value": r.taxable_value,
            "invoice_date": r.invoice_date.isoformat() if r.invoice_date else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
