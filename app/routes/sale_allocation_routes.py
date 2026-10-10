"""
Stage 3D routes.

  • POST /sale-allocations/sync      — idempotent bulk upsert of allocations, pools, claims
  • GET  /sale-allocations/{shop_id} — everything for the shop (reinstall / new phone)

Each row is committed on its own (same reasoning as purchase_batch_routes):
one bad row must not lose the rest, and a retry must be harmless.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_shop
from app.models.sale_allocation import SaleBatchAllocation, PdnGonePool, CostCorrectionClaim
from app.schemas.sale_allocation_schema import AllocationSyncRequest, AllocationSyncResponse
from app.util.time_utils import epoch_ms_to_local, local_now, local_to_epoch_ms

router = APIRouter(prefix="/sale-allocations", tags=["Sale Allocations"])
logger = logging.getLogger(__name__)


def _dt(ms):
    if not ms:
        return None
    try:
        return epoch_ms_to_local(ms)
    except (ValueError, OSError):
        return None


def _find(db, model, shop_id, origin, local_id):
    return db.query(model).filter(
        model.shop_id == shop_id, model.origin == origin, model.local_id == local_id
    ).first()


def _upsert(db, model, shop_id, origin, local_id, fields):
    row = _find(db, model, shop_id, origin, local_id)
    if row is None:
        row = model(shop_id=shop_id, origin=origin, local_id=local_id, **fields)
        db.add(row)
    else:
        for k, v in fields.items():
            setattr(row, k, v)
    db.flush()
    db.commit()
    return row


@router.post("/sync", response_model=AllocationSyncResponse)
def sync_sale_allocations(
    payload: AllocationSyncRequest,
    db: Session = Depends(get_db),
    current_shop=Depends(get_current_shop),
):
    out = AllocationSyncResponse()
    origin = (payload.origin or "")[:40]

    for a in payload.allocations:
        try:
            if a.quantity <= 0:
                logger.warning("[sale-allocations/sync] allocation %s has qty %s, ignored", a.local_id, a.quantity)
                out.allocation_ids.append(a.local_id)       # ack so the app stops retrying
                continue
            a.quantity_restored = min(max(a.quantity_restored, 0.0), a.quantity)
            _upsert(db, SaleBatchAllocation, current_shop.id, origin, a.local_id, dict(
                source_type=a.source_type, source_id=a.source_id,
                bill_number=a.bill_number, line_ordinal=a.line_ordinal,
                product_id=a.product_id, purchase_invoice_id=a.purchase_invoice_id,
                batch_local_id=a.batch_local_id,
                quantity=a.quantity, quantity_restored=a.quantity_restored,
                unit_cost_net=a.unit_cost_net, unit_cost_gross=a.unit_cost_gross,
                created_at=_dt(a.created_at) or local_now(),
            ))
            out.allocation_ids.append(a.local_id)
        except Exception as e:
            db.rollback()
            logger.error("[sale-allocations/sync] allocation %s failed: %s", a.local_id, e)

    for p in payload.pools:
        try:
            _upsert(db, PdnGonePool, current_shop.id, origin, p.local_id, dict(
                note_local_id=p.note_local_id, purchase_invoice_id=p.purchase_invoice_id,
                product_id=p.product_id, gone_qty=p.gone_qty, delta_gross=p.delta_gross,
                note_date=_dt(p.note_date) or local_now(),
            ))
            out.pool_ids.append(p.local_id)
        except Exception as e:
            db.rollback()
            logger.error("[sale-allocations/sync] pool %s failed: %s", p.local_id, e)

    for c in payload.claims:
        try:
            pool = _find(db, PdnGonePool, current_shop.id, origin, c.pool_local_id)
            if pool is None:
                # The pool has not arrived yet (or its purchase is not synced) - retry later.
                logger.info("[sale-allocations/sync] claim %s waits for pool %s", c.local_id, c.pool_local_id)
                continue
            amount = c.amount
            bad = (
                c.qty <= 0
                or c.qty > pool.gone_qty + 1e-6
                or amount * pool.delta_gross > 1e-9          # a claim always has the opposite sign of the note
            )
            if bad:
                logger.warning("[sale-allocations/sync] claim %s rejected (qty=%s amount=%s pool qty=%s delta=%s)",
                               c.local_id, c.qty, c.amount, pool.gone_qty, pool.delta_gross)
                out.claim_ids.append(c.local_id)            # ack: retrying cannot make it valid
                continue
            bound = c.qty * abs(pool.delta_gross) + 0.01
            if abs(amount) > bound:
                logger.warning("[sale-allocations/sync] claim %s amount %s clamped to %s", c.local_id, amount, bound)
                amount = bound if amount > 0 else -bound
            _upsert(db, CostCorrectionClaim, current_shop.id, origin, c.local_id, dict(
                allocation_local_id=c.allocation_local_id, pool_local_id=c.pool_local_id,
                note_local_id=c.note_local_id, product_id=c.product_id,
                qty=c.qty, amount=amount,
                claim_date=_dt(c.claim_date) or local_now(),
                source_type=c.source_type, source_id=c.source_id,
                bill_number=c.bill_number,
            ))
            out.claim_ids.append(c.local_id)
        except Exception as e:
            db.rollback()
            logger.error("[sale-allocations/sync] claim %s failed: %s", c.local_id, e)

    out.message = (
        f"{len(out.allocation_ids)}/{len(payload.allocations)} allocations, "
        f"{len(out.pool_ids)}/{len(payload.pools)} pools, "
        f"{len(out.claim_ids)}/{len(payload.claims)} claims accepted"
    )
    return out


def _ms(dt):
    return local_to_epoch_ms(dt) if dt else None


@router.get("/{shop_id}")
def list_sale_allocations(
    shop_id: int,
    after_alloc_id: int = 0,
    after_pool_id: int = 0,
    after_claim_id: int = 0,
    db: Session = Depends(get_db),
    current_shop=Depends(get_current_shop),
):
    if shop_id != current_shop.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-shop access denied")

    allocs = db.query(SaleBatchAllocation).filter(SaleBatchAllocation.shop_id == current_shop.id, SaleBatchAllocation.id > after_alloc_id).order_by(SaleBatchAllocation.id).all()
    pools = db.query(PdnGonePool).filter(PdnGonePool.shop_id == current_shop.id, PdnGonePool.id > after_pool_id).order_by(PdnGonePool.id).all()
    claims = db.query(CostCorrectionClaim).filter(CostCorrectionClaim.shop_id == current_shop.id, CostCorrectionClaim.id > after_claim_id).order_by(CostCorrectionClaim.id).all()
    return {
        "allocations": [
            {
                "id": a.id, "origin": a.origin, "local_id": a.local_id, "source_type": a.source_type, "source_id": a.source_id,
                "bill_number": a.bill_number, "line_ordinal": a.line_ordinal,
                "product_id": a.product_id, "purchase_invoice_id": a.purchase_invoice_id,
                "batch_local_id": a.batch_local_id, "quantity": a.quantity,
                "quantity_restored": a.quantity_restored,
                "unit_cost_net": a.unit_cost_net, "unit_cost_gross": a.unit_cost_gross,
                "created_at": _ms(a.created_at),
            } for a in allocs
        ],
        "pools": [
            {
                "id": p.id, "origin": p.origin, "local_id": p.local_id, "note_local_id": p.note_local_id,
                "purchase_invoice_id": p.purchase_invoice_id, "product_id": p.product_id,
                "gone_qty": p.gone_qty, "delta_gross": p.delta_gross, "note_date": _ms(p.note_date),
            } for p in pools
        ],
        "claims": [
            {
                "id": c.id, "origin": c.origin, "local_id": c.local_id, "allocation_local_id": c.allocation_local_id,
                "pool_local_id": c.pool_local_id, "note_local_id": c.note_local_id,
                "product_id": c.product_id, "qty": c.qty, "amount": c.amount,
                "claim_date": _ms(c.claim_date), "source_type": c.source_type, "source_id": c.source_id,
                "bill_number": c.bill_number,
            } for c in claims
        ],
    }
