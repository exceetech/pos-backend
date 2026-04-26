from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_shop
from app.models.shop import Shop
from app.schemas.shop_schema import ShopSettingsResponse, ShopSettingsUpdate

router = APIRouter(prefix="/shop", tags=["Shop"])


# ================= GET STORE SETTINGS =================

@router.get("/settings", response_model=ShopSettingsResponse)
def get_store_settings(
        current_shop: Shop = Depends(get_current_shop)
):

    return {
        "shop_name": current_shop.shop_name,
        "store_address": current_shop.store_address,
        "phone": current_shop.phone,
        "store_gstin": current_shop.store_gstin,
        "type": current_shop.type
    }


# ================= UPDATE STORE SETTINGS =================

@router.put("/settings")
def update_store_settings(
        data: ShopSettingsUpdate,
        db: Session = Depends(get_db),
        current_shop: Shop = Depends(get_current_shop)
):

    current_shop.shop_name = data.shop_name
    current_shop.store_address = data.store_address
    current_shop.phone = data.phone
    current_shop.store_gstin = data.store_gstin

    current_shop.type = data.type

    db.commit()
    db.refresh(current_shop)

    return {"message": "Store settings updated successfully"}