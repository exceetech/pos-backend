from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.dependencies import get_current_shop
from app.models.shop import Shop
from app.models.gst_profile import StoreGstProfile
from app.schemas.shop_schema import ShopSettingsResponse, ShopSettingsUpdate

router = APIRouter(prefix="/shop", tags=["Shop"])


# ================= GET STORE SETTINGS =================

@router.get("/settings")
def get_store_settings(
        db: Session = Depends(get_db),
        current_shop: Shop = Depends(get_current_shop)
):
    gst_profile = db.query(StoreGstProfile).filter(
        StoreGstProfile.shop_id == current_shop.id
    ).first()

    return {
        "shop_name": current_shop.shop_name,
        "store_address": current_shop.store_address,
        "phone": current_shop.phone,
        "store_gstin": current_shop.store_gstin,
        "type": current_shop.type,
        # GST profile enrichment (None-safe)
        "legal_name": gst_profile.legal_name if gst_profile else "",
        "trade_name": gst_profile.trade_name if gst_profile else "",
        "gst_scheme": gst_profile.gst_scheme if gst_profile else "",
        "registration_type": gst_profile.registration_type if gst_profile else "",
        "state_code": gst_profile.state_code if gst_profile else (
            current_shop.store_gstin[:2] if current_shop.store_gstin and len(current_shop.store_gstin) >= 2 else ""
        ),
        "gst_sync_status": gst_profile.sync_status if gst_profile else "pending"
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