from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from app.database import get_db
from app.models.sale_item import SaleItem
from app.models.inventory_log import InventoryLog
from app.dependencies import get_current_shop
from app.models.shop import Shop

router = APIRouter(prefix="/profit", tags=["Profit"])


@router.get("/")
def get_profit(
    filter: str = "all",
    start_date: str = None,
    end_date: str = None,
    db: Session = Depends(get_db),
    current_shop: Shop = Depends(get_current_shop)
):

    now = datetime.utcnow()

    # ================= DATE FILTER =================
    def apply_date_filter(query, column):
        if filter == "today":
            start = now.replace(hour=0, minute=0, second=0)
            return query.filter(column >= start)

        elif filter == "week":
            start = now - timedelta(days=7)
            return query.filter(column >= start)

        elif filter == "month":
            start = now.replace(day=1, hour=0, minute=0, second=0)
            return query.filter(column >= start)

        elif filter == "custom" and start_date and end_date:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
            return query.filter(column.between(start, end))

        return query

    # ================= SALES =================
    sales_query = db.query(SaleItem).filter(
        SaleItem.shop_id == current_shop.id
    )

    sales_query = apply_date_filter(sales_query, SaleItem.created_at)
    sales = sales_query.all()

    product_map = {}

    for s in sales:
        pid = s.product_id

        if pid not in product_map:
            product_map[pid] = {
                "product_id": pid,
                "product_name": s.product_name,
                "variant": s.variant,
                "qty": 0.0,
                "revenue": 0.0,
                "cost": 0.0,
                "profit": 0.0,
                "added": 0.0,
                "sold": 0.0,
                "remaining": 0.0,
                "lossQty": 0.0,
                "lossAmount": 0.0
            }

        product_map[pid]["qty"] += s.quantity
        product_map[pid]["revenue"] += s.total_revenue
        product_map[pid]["cost"] += s.total_cost
        product_map[pid]["profit"] += (s.total_revenue - s.total_cost)

    # ================= INVENTORY FILTER =================
    inventory_ids = db.query(InventoryLog.product_id).filter(
        InventoryLog.shop_id == current_shop.id,
        InventoryLog.is_active == True
    ).distinct().all()

    inventory_set = set(i.product_id for i in inventory_ids)

    product_map = {
        pid: data for pid, data in product_map.items()
        if pid in inventory_set
    }

    # ================= INVENTORY CALC =================
    total_loss = 0
    total_expense = 0

    for pid in product_map:

        logs_query = db.query(InventoryLog).filter(
            InventoryLog.product_id == pid,
            InventoryLog.shop_id == current_shop.id,
            InventoryLog.is_active == True
        )

        logs_query = apply_date_filter(logs_query, InventoryLog.created_at)
        logs = logs_query.all()

        added = sum(l.quantity for l in logs if l.type == "ADD")
        loss_qty = sum(l.quantity for l in logs if l.type == "LOSS")

        loss_amount = sum(l.quantity * l.price for l in logs if l.type == "LOSS")
        expense = sum(l.quantity * l.price for l in logs if l.type == "ADD")

        sold = product_map[pid]["qty"]
        remaining = added - sold - loss_qty

        product_map[pid]["added"] = added
        product_map[pid]["sold"] = sold
        product_map[pid]["remaining"] = remaining
        product_map[pid]["lossQty"] = loss_qty
        product_map[pid]["lossAmount"] = loss_amount

        total_loss += loss_amount
        total_expense += expense

    # ================= SUMMARY (FIXED) =================
    total_revenue = sum(p["revenue"] for p in product_map.values())
    total_cost = sum(p["cost"] for p in product_map.values())

    final_profit = total_revenue - total_cost - total_loss

    # ================= RESPONSE =================
    return {
        "summary": {
            "revenue": total_revenue,
            "cost": total_cost,
            "profit": final_profit,
            "loss": total_loss,
            "expense": total_expense
        },
        "products": list(product_map.values())
    }