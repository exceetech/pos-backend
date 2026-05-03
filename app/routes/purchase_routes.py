# routes/purchase.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime

from app.database import get_db
from app.dependencies import get_current_shop
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.schemas.purchase_schema import PurchaseSyncRequest, PurchaseSyncResponse

router = APIRouter(prefix="/purchases", tags=["Purchases"])


@router.post("/sync", response_model=PurchaseSyncResponse)
def sync_purchases(
    payload: PurchaseSyncRequest,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):
    purchase_id_map = {}
    success_count = 0

    for p in payload.purchases:

        # ✅ Create purchase header
        purchase = Purchase(
            shop_id=current_shop.id,
            invoice_number=p.invoice_number,
            supplier_gstin=p.supplier_gstin,
            supplier_name=p.supplier_name,
            state=p.state,
            taxable_amount=p.taxable_amount,
            cgst_percentage=p.cgst_percentage,
            sgst_percentage=p.sgst_percentage,
            igst_percentage=p.igst_percentage,
            cgst_amount=p.cgst_amount,
            sgst_amount=p.sgst_amount,
            igst_amount=p.igst_amount,
            invoice_value=p.invoice_value,
            created_at=datetime.utcfromtimestamp(p.created_at / 1000)
        )

        db.add(purchase)
        db.flush()  # 🔥 get purchase.id

        # ✅ Insert items
        for item in p.items:
            db.add(
                PurchaseItem(
                    purchase_id=purchase.id,
                    shop_product_id=item.shop_product_id,
                    product_name=item.product_name,
                    variant=item.variant,
                    hsn_code=item.hsn_code,
                    quantity=item.quantity,
                    unit=item.unit,
                    taxable_amount=item.taxable_amount,
                    invoice_value=item.invoice_value,
                    cost_price=item.cost_price,

                    purchase_cgst_percentage=item.purchase_cgst_percentage,
                    purchase_sgst_percentage=item.purchase_sgst_percentage,
                    purchase_igst_percentage=item.purchase_igst_percentage,

                    purchase_cgst_amount=item.purchase_cgst_amount,
                    purchase_sgst_amount=item.purchase_sgst_amount,
                    purchase_igst_amount=item.purchase_igst_amount,

                    sales_cgst_percentage=item.sales_cgst_percentage,
                    sales_sgst_percentage=item.sales_sgst_percentage,
                    sales_igst_percentage=item.sales_igst_percentage,
                )
            )

        purchase_id_map[str(p.local_id)] = purchase.id
        success_count += 1

    db.commit()

    return PurchaseSyncResponse(
        success_count=success_count,
        purchase_id_map=purchase_id_map
    )