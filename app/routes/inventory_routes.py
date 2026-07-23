from datetime import datetime, timezone
from app.util.time_utils import epoch_ms_to_local, local_now, local_to_epoch_ms, utc_to_epoch_ms, epoch_ms_to_utc

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_shop
from app.models.inventory import Inventory
from app.models.inventory_log import InventoryLog
from app.models.shop_products import ShopProduct
from app.schemas.inventory_schema import InventoryLogRequest

router = APIRouter(prefix="/inventory", tags=["Inventory"])


@router.post("/sync")
def sync_inventory_logs(
    logs: list[InventoryLogRequest],
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):
    print(f"[inventory/sync] shop_id={current_shop.id}, received {len(logs)} log(s)")

    # Issue 15: each log is now committed on its own (see the db.commit()
    # inside the loop below) instead of the whole batch sharing one
    # transaction committed at the very end. Same fix as Issue 12/11 —
    # otherwise an unexpected error partway through the batch (which used to
    # be entirely uncaught here) would 500 the whole request and discard
    # every log already processed earlier in the same batch, even though
    # the client would go on believing this sync had failed outright and
    # simply resend the same batch, unaware some of it had actually landed.
    for log in logs:
        try:
            print(f"  → product_id={log.product_id}, type={log.type}, qty={log.quantity}, price={log.price}, date={log.date}")

            # =================================================
            # 🔥 FK SAFETY CHECK (CRITICAL FIX)
            # =================================================
            product = db.query(ShopProduct).filter(
                ShopProduct.id == log.product_id,
                ShopProduct.shop_id == current_shop.id
            ).first()

            if not product:
                # skip invalid product instead of crashing
                print(f"  ⚠️  Skipping log for non-existent product_id={log.product_id}")
                continue

            # =================================================
            # 🔥 DEDUP CHECK (DATABASE LEVEL)
            # =================================================
            # We now check created_at to allow multiple identical transactions 
            # at different times (e.g. adding 10 units twice in a day).
            if log.date:
                log_date = epoch_ms_to_local(log.date)
            else:
                log_date = local_now()

            # Prefer the stable client idempotency key when present (Sync audit S2);
            # it survives timestamp drift and allows genuinely-identical transactions.
            # Fall back to the content+timestamp match for older clients.
            client_uid = getattr(log, "client_uid", None)
            if client_uid:
                existing_log = db.query(InventoryLog).filter(
                    InventoryLog.shop_id == current_shop.id,
                    InventoryLog.client_uid == client_uid
                ).first()
            else:
                existing_log = db.query(InventoryLog).filter(
                    InventoryLog.shop_id == current_shop.id,
                    InventoryLog.product_id == log.product_id,
                    InventoryLog.type == log.type,
                    InventoryLog.quantity == log.quantity,
                    InventoryLog.price == log.price,
                    InventoryLog.created_at == log_date
                ).first()

            if existing_log:
                continue  # already synced

            # =================================================
            # 🔥 SAVE LOG
            # =================================================
            db_log = InventoryLog(
                shop_id=current_shop.id,
                product_id=log.product_id,
                type=log.type,
                quantity=log.quantity,
                price=log.price,
                created_at=log_date,
                client_uid=client_uid
            )
            db.add(db_log)

            # =================================================
            # 🔥 GET / CREATE INVENTORY
            # =================================================
            inventory = db.query(Inventory).filter(
                Inventory.product_id == log.product_id,
                Inventory.shop_id == current_shop.id
            ).first()

            if not inventory:
                inventory = Inventory(
                    product_id=log.product_id,
                    shop_id=current_shop.id,
                    current_stock=0,
                    average_cost=0,
                    is_active=True
                )
                db.add(inventory)
                db.flush() # 🔥 ensure subsequent logs in the same loop find this row
            else:
                inventory.is_active = True

            # =================================================
            # 🔥 APPLY LOGIC
            # =================================================

            if log.type in ["ADD", "PURCHASE", "RETURN", "CANCEL_RESTOCK"]:

                old_stock = float(inventory.current_stock or 0.0)
                old_avg = float(inventory.average_cost or 0.0)

                new_stock = old_stock + log.quantity

                if log.price <= 0:
                    new_avg = old_avg
                elif old_stock <= 0:
                    new_avg = log.price
                elif new_stock <= 0:
                    new_avg = log.price
                else:
                    new_avg = ((old_stock * old_avg) + (log.quantity * log.price)) / new_stock

                inventory.current_stock = new_stock
                inventory.average_cost = new_avg

            # PURCHASE_RETURN (stock going back to a supplier) is subtractive,
            # same as SALE/LOSS. It used to be bundled into the "RETURN"
            # bucket above, which is additive — every purchase return synced
            # to the backend was ADDING quantity instead of removing it (e.g.
            # purchase 200, sell 50 -> 150, return 60 then 10 should end at
            # 80 but the additive bug produced 220). "RETURN" itself is kept
            # in the additive bucket, reserved for a future genuine
            # additive case (customer returns an item to the shop) — no
            # code path currently writes it.
            elif log.type in ["SALE", "LOSS", "PURCHASE_RETURN"]:
                new_stock = float(inventory.current_stock or 0.0) - log.quantity
                inventory.current_stock = new_stock

            elif log.type == "ADJUST":
                # Report 5 fix: ADJUST used to share the SALE/LOSS subtraction
                # branch above, but it is NOT a delta — it's a manual physical
                # stock-count correction (InventoryManager.resetStock on the
                # client), and log.quantity carries the ABSOLUTE corrected
                # count, not an amount to subtract. Treating it as subtractive
                # meant correcting a product's stock from, say, 5 to 100 wrote
                # new_stock = 5 - 100 = -95 to the backend instead of 100 — so
                # the exact tool a shop reaches for to fix a wrong stock number
                # was actively corrupting it further, often into negative
                # territory. Now sets the stock directly, matching the
                # absolute-checkpoint semantics already used correctly in
                # profit_routes.py's own ADJUST handling.
                inventory.current_stock = log.quantity
                if log.price > 0:
                    inventory.average_cost = log.price

            # Commit this log on its own instead of batching every log
            # into one transaction committed at the very end — a plain
            # rollback() undoes the WHOLE transaction, not just the
            # failed statement, so a shared transaction would silently
            # wipe out every log that had already succeeded earlier in
            # the same batch.
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"  ⚠️  Skipping log for product_id={log.product_id}: {e}")

    return {"message": "Inventory synced successfully"}

@router.get("/my")
def get_inventory(
    updated_since: int = 0,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):
    # Delta pull (Sync audit S5): when the client sends its cursor we return only
    # rows changed since then. `>=` (not `>`) so rows sharing the cursor's exact
    # timestamp — common when a batch commits in the same instant — are never
    # skipped; the client upsert dedupes the small overlap. updated_since=0
    # (default / old clients) returns everything → backward-compatible.
    query = db.query(Inventory).join(
        ShopProduct,
        Inventory.product_id == ShopProduct.id
    ).filter(
        Inventory.shop_id == current_shop.id,
        ShopProduct.is_active == True
    )

    if updated_since > 0:
        query = query.filter(Inventory.updated_at >= epoch_ms_to_utc(updated_since))

    inventory = query.all()

    response = []
    for item in inventory:
        response.append({
            "product_id": item.product_id,
            "stock": float(item.current_stock or 0),
            "avg_cost": float(item.average_cost or 0),
            # Real flag, not a hardcoded True (R5) — the client maps this onto the
            # local inventory row, so it must reflect the actual state.
            "is_active": bool(item.is_active),
            "updated_at": utc_to_epoch_ms(item.updated_at) if item.updated_at else None
        })
    return response


@router.get("/logs")
def get_inventory_logs(
    after_id: int = 0,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):
    # Delta pull (Sync audit S5): logs are append-only and `id` is a
    # server-monotonic autoincrement, so it's a safe cursor (event time is not —
    # backdated rows would be skipped). after_id=0 (default / old clients) returns
    # everything, so this stays backward-compatible.
    logs = db.query(InventoryLog).filter(
        InventoryLog.shop_id == current_shop.id,
        InventoryLog.id > after_id,
    ).order_by(InventoryLog.id).all()

    return [
        {
            "id": log.id,
            "product_id": log.product_id,
            "type": log.type,
            "quantity": log.quantity,
            # created_at is an EVENT time stored as shop-local wall clock
            # (Phase 1). Serialize via local_to_epoch_ms so it round-trips to the
            # same instant the client sent, keeping content-dedupe stable (M2).
            "date": local_to_epoch_ms(log.created_at) if log.created_at else None
        }
        for log in logs
    ]