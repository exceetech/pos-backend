from app.models.shop_products import ShopProduct
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.util.time_utils import local_now

from app.database import get_db
from app.models.sale_item import SaleItem
from app.models.inventory_log import InventoryLog
from app.dependencies import get_current_shop
from app.models.shop import Shop
from app.models.credit_note import CreditNote, CreditNoteItem

router = APIRouter(prefix="/profit", tags=["Profit"])


@router.get("/")
def get_profit(
    filter: str = "all",
    start_date: str = None,
    end_date: str = None,
    db: Session = Depends(get_db),
    current_shop: Shop = Depends(get_current_shop)
):

    now = local_now()

    # ================= DATE FILTER =================
    def apply_date_filter(query, column):

        if filter == "today":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            return query.filter(column >= start)

        elif filter == "week":
            start = now - timedelta(days=7)
            return query.filter(column >= start)

        elif filter == "month":
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            return query.filter(column >= start)

        elif filter == "custom" and start_date and end_date:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
            return query.filter(column >= start, column < end)

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

            product = db.query(ShopProduct).filter(

                ShopProduct.id == s.product_id

            ).first()
            
            product_map[pid] = {
                "product_id": pid,
                "product_name": s.product_name,
                "variant": s.variant,
                "unit": product.unit,
                "qty": 0.0,
                "revenue": 0.0,
                "cost": 0.0,
                "profit": 0.0,
                "added": 0.0,
                "sold": 0.0,
                "lossAmount": 0.0,
                "returned_qty": 0.0,
                "returned_cost": 0.0
            }

        product_map[pid]["qty"] += s.quantity
        product_map[pid]["revenue"] += s.total_revenue
        product_map[pid]["cost"] += s.total_cost
        product_map[pid]["profit"] += (s.total_revenue - s.total_cost)

    # ================= RETURNS =================
    returns_query = db.query(CreditNoteItem).join(
        CreditNote, CreditNote.id == CreditNoteItem.note_id
    ).filter(
        CreditNote.shop_id == current_shop.id
    )

    returns_query = apply_date_filter(returns_query, CreditNote.created_at)
    returns = returns_query.all()

    for r in returns:
        pid = r.product_id
        if pid not in product_map:
            product = db.query(ShopProduct).filter(
                ShopProduct.id == pid
            ).first()
            
            if not product:
                continue

            product_map[pid] = {
                "product_id": pid,
                "product_name": r.product_name,
                "variant": r.variant,
                "unit": product.unit if product.unit else "",
                "qty": 0.0,
                "revenue": 0.0,
                "cost": 0.0,
                "profit": 0.0,
                "added": 0.0,
                "sold": 0.0,
                "lossAmount": 0.0,
                "returned_qty": 0.0,
                "returned_cost": 0.0
            }

        qty_returned = r.quantity_returned
        rev_returned = float(r.total_amount)       # Gross Revenue returned
        cost_returned = float(r.cost_price_used)   # Net Cost returned

        product_map[pid]["qty"] -= qty_returned
        product_map[pid]["revenue"] -= rev_returned
        product_map[pid]["cost"] -= cost_returned
        product_map[pid]["profit"] -= (rev_returned - cost_returned)
        
        product_map[pid]["returned_qty"] += qty_returned
        product_map[pid]["returned_cost"] += cost_returned

    # ================= INVENTORY FILTER (NO DATE FILTER HERE) =================
    inventory_ids = db.query(InventoryLog.product_id).filter(
        InventoryLog.shop_id == current_shop.id,
        InventoryLog.is_active == True
    ).distinct().all()

    inventory_set = set(i.product_id for i in inventory_ids)

    product_map = {
        pid: data for pid, data in product_map.items()
        if pid in inventory_set
    }

    # ================= INVENTORY CALCULATIONS =================
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

        raw_added = sum(l.quantity for l in logs if l.type == "ADD")
        loss_qty = sum(l.quantity for l in logs if l.type == "LOSS")

        loss_amount = sum(l.quantity * l.price for l in logs if l.type == "LOSS")
        raw_expense = sum(l.quantity * l.price for l in logs if l.type == "ADD")

        # Clean genuine purchases by stripping out returned stock
        added = raw_added - product_map[pid].get("returned_qty", 0.0)
        expense = raw_expense - product_map[pid].get("returned_cost", 0.0)

        sold = product_map[pid]["qty"]
        remaining = added - sold - loss_qty

        product_map[pid]["added"] = added
        product_map[pid]["sold"] = sold
        product_map[pid]["remaining"] = remaining
        product_map[pid]["lossQty"] = loss_qty
        product_map[pid]["lossAmount"] = loss_amount

        total_loss += loss_amount
        total_expense += expense

    # ================= SUMMARY =================
    total_revenue = sum(p["revenue"] for p in product_map.values())
    total_cost = sum(p["cost"] for p in product_map.values())

    final_profit = total_revenue - total_cost - total_loss

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