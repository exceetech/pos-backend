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

    for log in logs:

        # =================================================
        # 🔥 FK SAFETY CHECK (CRITICAL FIX)
        # =================================================
        product = db.query(ShopProduct).filter(
            ShopProduct.id == log.product_id,
            ShopProduct.shop_id == current_shop.id
        ).first()

        if not product:
            # skip invalid product instead of crashing
            continue

        # =================================================
        # 🔥 DEDUP CHECK (DATABASE LEVEL)
        # =================================================
        existing_log = db.query(InventoryLog).filter(
            InventoryLog.shop_id == current_shop.id,
            InventoryLog.product_id == log.product_id,
            InventoryLog.type == log.type,
            InventoryLog.quantity == log.quantity,
            InventoryLog.price == log.price
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

            created_at=log.date or datetime.utcnow()

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

        elif log.type in ["SALE", "LOSS", "ADJUST"]:

            # 🔥 PREVENT NEGATIVE STOCK
            inventory.current_stock = max(
                0,
                inventory.current_stock - log.quantity
            )

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