"""
Money Book sync (payment & cash-flow tracking).

  • POST /money-entries/sync      — idempotent bulk upsert, keyed by (shop, uid)
  • GET  /money-entries/{shop_id} — rows for the shop (reinstall / new phone), paged by id

The report and the statement are computed on the phone; this table is the backup and the
source for restoring a new phone. Rows are append-only: a retried push never changes an amount.
Each row is committed on its own so one bad row cannot lose the rest.
"""
import logging
import math

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_shop
from app.models.money_entry import MoneyEntry
from app.schemas.money_entry_schema import MoneyEntrySyncRequest, MoneyEntrySyncResponse
from app.util.time_utils import epoch_ms_to_local, local_now, local_to_epoch_ms

router = APIRouter(prefix="/money-entries", tags=["Money Book"])
logger = logging.getLogger(__name__)

DIRECTIONS = {"IN", "OUT"}
MODES = {"CASH", "UPI", "CARD", "BANK"}
STATUSES = {"RECEIVED", "PENDING", "CANCELLED"}
REASONS = {
    "SALE", "SALE_REFUND", "SALE_EXTRA", "DUES_RECEIVED", "ADVANCE_REFUND",
    "PURCHASE_PAID", "SUPPLIER_PAID", "PURCHASE_REFUND", "OPENING", "MANUAL", "TRANSFER",
}
SOURCES = {
    "BILL", "CREDIT_NOTE", "DEBIT_NOTE", "CREDIT_TXN", "PURCHASE",
    "PURCHASE_RETURN", "PURCHASE_NOTE", "MANUAL",
}
MAX_AMOUNT = 1_000_000_000.0
PAGE_MAX = 1000


def _dt(ms):
    if not ms:
        return None
    try:
        return epoch_ms_to_local(ms)
    except (ValueError, OSError):
        return None


def _reject_reason(e):
    """Why a row can never be valid (retrying cannot fix it), or None."""
    if e.direction not in DIRECTIONS:
        return f"direction {e.direction}"
    if e.mode not in MODES:
        return f"mode {e.mode}"
    if e.reason not in REASONS:
        return f"reason {e.reason}"
    if e.source_type not in SOURCES or e.parent_type not in SOURCES:
        return f"source {e.source_type}/{e.parent_type}"
    if e.status not in STATUSES:
        return f"status {e.status}"
    if not e.uid or len(e.uid) > 40:
        return "uid"
    if math.isnan(e.amount) or math.isinf(e.amount) or round(e.amount, 2) <= 0 or e.amount > MAX_AMOUNT:
        return f"amount {e.amount}"
    return None


@router.post("/sync", response_model=MoneyEntrySyncResponse)
def sync_money_entries(
    payload: MoneyEntrySyncRequest,
    db: Session = Depends(get_db),
    current_shop=Depends(get_current_shop),
):
    out = MoneyEntrySyncResponse()
    origin = (payload.origin or "")[:40]

    for e in payload.entries:
        try:
            why = _reject_reason(e)
            if why:
                logger.warning("[money-entries/sync] row %s rejected (%s)", e.uid, why)
                out.uids.append(e.uid)               # ack: retrying cannot make it valid
                continue
            row = db.query(MoneyEntry).filter(
                MoneyEntry.shop_id == current_shop.id, MoneyEntry.uid == e.uid
            ).first()
            if row is None:
                db.add(MoneyEntry(
                    shop_id=current_shop.id, uid=e.uid, origin=origin, local_id=e.local_id,
                    direction=e.direction, mode=e.mode, amount=round(e.amount, 2), reason=e.reason,
                    source_type=e.source_type, source_id=e.source_id,
                    parent_type=e.parent_type, parent_id=e.parent_id,
                    party_name=e.party_name[:120], ref_text=e.ref_text[:60],
                    status=e.status, created_at=_dt(e.created_at) or local_now(),
                ))
            else:
                # Append-only: amount / mode / direction / reason never change. Only a payment link
                # being paid (PENDING -> RECEIVED) and the descriptive text may be updated.
                if row.status == "PENDING" and e.status in ("RECEIVED", "CANCELLED"):
                    row.status = e.status
                if e.party_name:
                    row.party_name = e.party_name[:120]
                if e.ref_text:
                    row.ref_text = e.ref_text[:60]
            db.flush()
            db.commit()
            out.uids.append(e.uid)
        except Exception as ex:
            db.rollback()
            logger.error("[money-entries/sync] row %s failed: %s", e.uid, ex)

    out.message = f"{len(out.uids)}/{len(payload.entries)} money entries accepted"
    return out


@router.get("/{shop_id}")
def list_money_entries(
    shop_id: int,
    after_id: int = 0,
    limit: int = 500,
    db: Session = Depends(get_db),
    current_shop=Depends(get_current_shop),
):
    if shop_id != current_shop.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-shop access denied")
    limit = max(1, min(limit, PAGE_MAX))
    rows = (
        db.query(MoneyEntry)
        .filter(MoneyEntry.shop_id == current_shop.id, MoneyEntry.id > after_id)
        .order_by(MoneyEntry.id)
        .limit(limit)
        .all()
    )
    return {
        "entries": [
            {
                "id": r.id, "uid": r.uid, "origin": r.origin, "local_id": r.local_id,
                "direction": r.direction, "mode": r.mode, "amount": float(r.amount), "reason": r.reason,
                "source_type": r.source_type, "source_id": r.source_id,
                "parent_type": r.parent_type, "parent_id": r.parent_id,
                "party_name": r.party_name, "ref_text": r.ref_text, "status": r.status,
                "created_at": local_to_epoch_ms(r.created_at) if r.created_at else None,
            } for r in rows
        ],
        "has_more": len(rows) == limit,
    }
