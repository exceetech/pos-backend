from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.sale_item import SaleItem
from app.schemas.sale_schema import CreateSaleRequest
from app.dependencies import get_current_shop
from app.models.shop import Shop

router = APIRouter(prefix="/sales", tags=["Sales"])


@router.post("/create")
def create_sale(
    data: CreateSaleRequest,
    db: Session = Depends(get_db),
    current_shop: Shop = Depends(get_current_shop)
):

    # Idempotency guard (Report 5 fix): this endpoint used to be called
    # exactly once, fire-and-forget, with no retry on failure and no way
    # to safely retry later — a flaky connection meant the sale silently
    # never reached profit analytics. Now that the app backfills failed
    # pushes via SyncManager, a retried/backfilled call for the same local
    # sale must not insert a second batch of rows.
    if data.client_bill_id is not None and data.client_device_id:
        existing = db.query(SaleItem).filter(
            SaleItem.shop_id == current_shop.id,
            SaleItem.client_bill_id == data.client_bill_id,
            SaleItem.client_device_id == data.client_device_id,
        ).first()
        if existing:
            return {"success": True, "message": "Sale already recorded"}

    for item in data.items:

        sale = SaleItem(
            shop_id=current_shop.id,
            product_id=item.product_id,
            product_name=item.product_name,
            variant=item.variant,
            quantity=item.quantity,
            selling_price=item.selling_price,
            cost_price=item.cost_price,
            total_revenue=item.quantity * item.selling_price,
            total_cost=item.quantity * item.cost_price,
            bill_number=data.bill_number,
            client_bill_id=data.client_bill_id,
            client_device_id=data.client_device_id,
        )

        db.add(sale)

    db.commit()

    return {"success": True}