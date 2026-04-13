from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.bill import Bill
from app.models.bill_items import BillItem
from app.models.shop_products import ShopProduct
from app.models.global_products import GlobalProduct
from app.models.billing_settings import BillingSettings

from app.schemas.bill_schema import CreateBillRequest
from app.dependencies import get_current_shop

router = APIRouter(prefix="/bills", tags=["Bills"])


# ================= CREATE BILL =================

@router.post("/create")
def create_bill(
    data: CreateBillRequest,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):

    total_amount = 0.0
    total_items = 0.0
    discount = data.discount or 0.0

    # 🔥 BILL NUMBER
    last_bill = db.query(Bill).filter(
        Bill.shop_id == current_shop.id
    ).order_by(Bill.id.desc()).first()

    next_bill_number = 500000 if not last_bill else int(last_bill.bill_number) + 1

    # 🔥 GST SETTINGS
    settings = db.query(BillingSettings).filter(
        BillingSettings.shop_id == current_shop.id
    ).first()

    gst_rate = settings.default_gst if settings else 0

    bill_items = []

    for item in data.items:

        product = db.query(ShopProduct, GlobalProduct).join(
            GlobalProduct,
            ShopProduct.global_product_id == GlobalProduct.id
        ).filter(
            ShopProduct.id == item.shop_product_id,
            ShopProduct.shop_id == current_shop.id,
            ShopProduct.is_active == True
        ).first()

        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        shop_product, global_product = product

        # ✅ NO CONVERSION (IMPORTANT)
        quantity = item.quantity

        subtotal = shop_product.price * quantity

        total_amount += subtotal
        total_items += quantity

        bill_items.append({
            "product_name": global_product.name,
            "price": shop_product.price,
            "quantity": quantity,
            "unit": shop_product.unit or "unit",
            "variant": item.variant,
            "subtotal": subtotal,
            "shop_product_id": shop_product.id
        })

    # 🔥 GST
    gst = total_amount * gst_rate / 100
    final_total = total_amount + gst - discount

    bill = Bill(
        shop_id=current_shop.id,
        bill_number=str(next_bill_number),
        total_amount=final_total,
        total_items=total_items,   # ✅ FLOAT
        payment_method=data.payment_method,
        gst=gst,
        discount=discount
    )

    db.add(bill)
    db.commit()
    db.refresh(bill)

    # 🔥 INSERT BILL ITEMS
    for i in bill_items:

        bill_item = BillItem(
            bill_id=bill.id,
            shop_product_id=i["shop_product_id"],
            product_name=i["product_name"],
            price=i["price"],
            quantity=i["quantity"],
            unit=i["unit"],
            variant=i.get("variant"),
            subtotal=i["subtotal"]
        )

        db.add(bill_item)

    db.commit()

    return {
        "message": "Bill created successfully",
        "bill_id": bill.id,
        "bill_number": bill.bill_number,
        "total_amount": final_total
    }


# ================= GET SINGLE BILL =================

@router.get("/{bill_id}")
def get_bill(
    bill_id: int,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):

    bill = db.query(Bill).filter(
        Bill.id == bill_id,
        Bill.shop_id == current_shop.id,
        Bill.active == True
    ).first()

    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")

    items = db.query(BillItem).filter(
        BillItem.bill_id == bill_id
    ).all()

    return {
        "bill": {
            "bill_id": bill.id,
            "bill_number": bill.bill_number,
            "subtotal": bill.total_amount - bill.gst + bill.discount,
            "gst": bill.gst,
            "discount": bill.discount,
            "total_amount": bill.total_amount,
            "payment_method": bill.payment_method,
            "created_at": str(bill.created_at)
        },
        "items": [
            {
                "product_name": item.product_name,
                "price": item.price,
                "quantity": item.quantity,
                "unit": item.unit,
                "variant": item.variant,
                "shop_product_id": item.shop_product_id,
                "subtotal": item.subtotal
            }
            for item in items
        ]
    }


# ================= GET ALL BILLS =================

@router.get("")
def get_bills(
    date: str | None = None,
    item: str | None = None,
    payment: str | None = None,
    sort: str | None = None,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):

    query = db.query(Bill).filter(
        Bill.shop_id == current_shop.id,
        Bill.active == True
    )

    if payment:
        query = query.filter(Bill.payment_method == payment)

    if date:
        query = query.filter(Bill.created_at.like(f"{date}%"))

    if item:
        query = query.join(BillItem).filter(
            BillItem.product_name.ilike(f"%{item}%")
        ).distinct()

    if sort == "amount":
        query = query.order_by(Bill.total_amount.desc())
    else:
        query = query.order_by(Bill.created_at.desc())

    bills = query.all()

    return [
        {
            "bill_id": b.id,
            "bill_number": b.bill_number,
            "total_amount": b.total_amount,
            "payment_method": b.payment_method,
            "created_at": str(b.created_at)
        }
        for b in bills
    ]