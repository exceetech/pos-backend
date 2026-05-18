# routes/purchase.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import datetime

from app.database import get_db
from app.dependencies import get_current_shop
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.purchase_batch import PurchaseBatch
from app.models.credit import CreditAccount
from app.schemas.purchase_schema import PurchaseSyncRequest, PurchaseSyncResponse
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/purchases", tags=["Purchases"])


@router.post("/sync", response_model=PurchaseSyncResponse)
def sync_purchases(
    payload: PurchaseSyncRequest,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):
    purchase_id_map = {}
    success_count = 0

    try:
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
                invoice_date=(
                    datetime.utcfromtimestamp(p.invoice_date / 1000)
                    if p.invoice_date else None
                ),
                is_credit=1 if p.is_credit else 0,
                credit_account_id=p.credit_account_id,
                created_at=datetime.utcfromtimestamp(p.created_at / 1000)
            )

            # ✅ Validation: Ensure credit account exists and belongs to this shop
            if purchase.credit_account_id and purchase.credit_account_id > 0:
                acc = db.query(CreditAccount).filter(
                    CreditAccount.id == purchase.credit_account_id,
                    CreditAccount.shop_id == current_shop.id
                ).first()
                if not acc:
                    return JSONResponse(
                        status_code=400,
                        content={"message": f"Credit account {purchase.credit_account_id} not found for this shop"}
                    )

            db.add(purchase)
            db.flush()

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

                # ✅ Auto-create PurchaseBatch for Hybrid Inventory
                if item.shop_product_id:
                    unit_cost = (item.taxable_amount / item.quantity) if item.quantity > 0 else 0.0
                    gst_pct = item.purchase_cgst_percentage + item.purchase_sgst_percentage + item.purchase_igst_percentage

                    db.add(
                        PurchaseBatch(
                            shop_id=current_shop.id,
                            local_id=item.local_id,
                            product_id=item.shop_product_id,
                            purchase_invoice_id=purchase.id,
                            supplier_name=p.supplier_name,
                            supplier_gstin=p.supplier_gstin,
                            invoice_number=p.invoice_number,
                            batch_code=p.invoice_number,
                            quantity_purchased=item.quantity,
                            quantity_remaining=item.quantity,
                            unit_cost_excluding_tax=unit_cost,
                            gst_percent=gst_pct,
                            cgst_percent=item.purchase_cgst_percentage,
                            sgst_percent=item.purchase_sgst_percentage,
                            igst_percent=item.purchase_igst_percentage,
                            invoice_value=item.invoice_value,
                            taxable_value=item.taxable_amount,
                            invoice_date=purchase.invoice_date,
                            created_at=purchase.created_at
                        )
                    )

            purchase_id_map[str(p.local_id)] = purchase.id
            success_count += 1

        db.commit()

    except IntegrityError as e:
        db.rollback()
        return JSONResponse(
            status_code=400,
            content={"message": f"Database integrity error: {str(e.orig)}"}
        )
    except Exception as e:
        db.rollback()
        return JSONResponse(
            status_code=500,
            content={"message": f"Server error during purchase sync: {str(e)}"}
        )

    return PurchaseSyncResponse(
        success_count=success_count,
        purchase_id_map=purchase_id_map
    )