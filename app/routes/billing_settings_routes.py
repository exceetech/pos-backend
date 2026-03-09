from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.billing_settings import BillingSettings
from app.schemas.billing_settings_schema import BillingSettingsResponse, BillingSettingsUpdate

from app.dependencies import get_current_shop

router = APIRouter(prefix="/billing-settings", tags=["Billing Settings"])


@router.get("", response_model=BillingSettingsResponse)
def get_settings(
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):

    settings = db.query(BillingSettings).filter(
        BillingSettings.shop_id == current_shop.id
    ).first()

    # create default settings if not exists
    if not settings:

        settings = BillingSettings(
            shop_id=current_shop.id,
            default_gst=0,
            printer_layout="80mm"
        )

        db.add(settings)
        db.commit()
        db.refresh(settings)

    return settings


@router.put("")
def update_settings(
    data: BillingSettingsUpdate,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):

    settings = db.query(BillingSettings).filter(
        BillingSettings.shop_id == current_shop.id
    ).first()

    if not settings:
        settings = BillingSettings(shop_id=current_shop.id)
        db.add(settings)

    settings.default_gst = data.default_gst
    settings.printer_layout = data.printer_layout

    db.commit()

    return {"message": "Billing settings updated"}