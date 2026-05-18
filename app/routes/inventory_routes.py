from datetime import datetime

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

    for log in logs:
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
            log_date = datetime.utcfromtimestamp(log.date / 1000.0)
        else:
            log_date = datetime.utcnow()

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
            created_at=log_date
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

        # =================================================
        # 🔥 APPLY LOGIC
        # =================================================

        if log.type == "ADD":

            old_stock = inventory.current_stock
            old_avg = inventory.average_cost

            new_stock = old_stock + log.quantity

            new_avg = (
                ((old_stock * old_avg) + (log.quantity * log.price))
                / new_stock
            ) if new_stock > 0 else log.price

            inventory.current_stock = new_stock
            inventory.average_cost = new_avg

        elif log.type in ["SALE", "LOSS", "ADJUST", "RETURN"]:
            # 🔥 PREVENT NEGATIVE STOCK & RESET COST IF 0
            new_stock = max(0.0, float(inventory.current_stock or 0) - log.quantity)
            inventory.current_stock = new_stock
            if new_stock <= 0:
                inventory.average_cost = 0.0

    db.commit()

    return {"message": "Inventory synced successfully"}

@router.get("/my")
def get_inventory(
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):
    inventory = db.query(Inventory).filter(
        Inventory.shop_id == current_shop.id,
        Inventory.is_active == True
    ).all()

    response = []

    for item in inventory:
        response.append({
            "product_id": item.product_id,
            "stock": float(item.current_stock or 0),
            "avg_cost": float(item.average_cost or 0),
            "is_active": item.is_active
        })
    return response