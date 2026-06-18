import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.bill_items import BillItem
from app.models.shop_products import ShopProduct
from app.models.global_products import GlobalProduct

from app.dependencies import get_current_shop
from app.models.bill import Bill
from app.util.ai_cache import report_cache as _report_cache

logger = logging.getLogger(__name__)

router = APIRouter()




@router.get("/analytics/ai-report")
def get_ai_report(
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):
    from app.services.insights_service import generate_structured_insights

    shop_id = None
    try:
        shop_id = current_shop.id
        report_data = _report_cache.get(shop_id)
        if report_data is None:
            results = (
                db.query(
                    GlobalProduct.name.label("product"),
                    func.sum(BillItem.quantity).label("quantity"),
                    # BillItem.total_amount is already the GST-inclusive,
                    # discount-applied line total, so no gross-up ratio is needed
                    # (the old subtotal * (total/(total-gst+discount)) expression).
                    func.sum(BillItem.total_amount).label("revenue")
                )
                .join(Bill, Bill.id == BillItem.bill_id)
                .join(ShopProduct, ShopProduct.id == BillItem.shop_product_id)
                .join(GlobalProduct, GlobalProduct.id == ShopProduct.global_product_id)
                .filter(
                    ShopProduct.shop_id == shop_id,
                    Bill.active == True
                )
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
            _report_cache.set(shop_id, report_data)

        insights = generate_structured_insights(db, shop_id)
        
        return {
            "insights": insights,
            "report_data": report_data,
            "ai_report": "New insights system is active. See cards below."
        }
    except Exception:
        # Log the full traceback so the failure is diagnosable, and surface a real
        # error status so the client can fall back to its cache / error state instead
        # of mistaking a server failure for "no data".
        logger.exception("AI report generation failed for shop %s", shop_id)
        raise HTTPException(status_code=500, detail="Failed to generate AI report")
