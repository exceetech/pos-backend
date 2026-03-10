from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.bill_items import BillItem
from app.models.shop_products import ShopProduct
from app.models.global_products import GlobalProduct

from app.services.ai_service import generate_ai_insights
from app.dependencies import get_current_shop

router = APIRouter()


@router.get("/analytics/ai-report")
def get_ai_report(
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):

    shop_id = current_shop.id

    results = (
        db.query(
            GlobalProduct.name.label("product"),
            func.sum(BillItem.quantity).label("quantity"),
            func.sum(BillItem.subtotal).label("revenue")
        )
        .join(ShopProduct, ShopProduct.id == BillItem.shop_product_id)
        .join(GlobalProduct, GlobalProduct.id == ShopProduct.global_product_id)
        .filter(ShopProduct.shop_id == shop_id)
        .group_by(GlobalProduct.name)
        .all()
    )

    report_data = [
        {
            "product": r.product,
            "quantity": int(r.quantity or 0),
            "revenue": float(r.revenue or 0)
        }
        for r in results
    ]

    # If no sales yet
    if not report_data:
        return {
            "report_data": [],
            "ai_report": "No sales data yet. Start selling to generate AI insights."
        }

    insights = generate_ai_insights(report_data)

    return {
        "report_data": report_data,
        "ai_report": insights
    }