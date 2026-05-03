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
            total_cost=item.quantity * item.cost_price
        )

        db.add(sale)

    db.commit()

    return {"success": True}