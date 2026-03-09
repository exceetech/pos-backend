from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_shop
from app.models.bill import Bill
from app.schemas.security_schema import ChangePasswordRequest
from app.models.shop import Shop

from app.models.shop_products import ShopProduct
from app.models.billing_settings import BillingSettings
from app.security import hash_password

router = APIRouter(prefix="/security", tags=["Security"])


@router.put("/clear-bills")
def clear_bills(
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):

    bills = db.query(Bill).filter(
        Bill.shop_id == current_shop.id,
        Bill.active == True
    ).all()

    for bill in bills:
        bill.active = False

    db.commit()

    return {"message": "All bills archived successfully"}



@router.put("/change-password")
def change_password(
    data: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):

    current_shop.password_hash = hash_password(data.new_password)

    db.commit()

    return {"message": "Password updated successfully"}



@router.put("/factory-reset")
def factory_reset(
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):

    # deactivate bills
    bills = db.query(Bill).filter(
        Bill.shop_id == current_shop.id
    ).all()

    for bill in bills:
        bill.active = False


    # deactivate products
    products = db.query(ShopProduct).filter(
        ShopProduct.shop_id == current_shop.id
    ).all()

    for p in products:
        p.is_active = False


    # remove billing settings
    db.query(BillingSettings).filter(
        BillingSettings.shop_id == current_shop.id
    ).delete()

    db.commit()

    return {"message": "Factory reset completed"}