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

    # Built explicitly (not a bare ORM passthrough) — razorpay_configured
    # is computed, not a real column, and key_secret/webhook_secret must
    # never end up in this response even if a future field gets added
    # carelessly to the ORM model.
    return BillingSettingsResponse(
        default_gst=settings.default_gst,
        printer_layout=settings.printer_layout,
        razorpay_key_id=settings.razorpay_key_id,
        razorpay_configured=bool(
            settings.razorpay_key_id and settings.razorpay_key_secret and settings.razorpay_webhook_secret
        ),
    )


@router.put("", response_model=BillingSettingsResponse)
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

    # Write-only, and only when actually sent — None means "leave
    # whatever's already saved alone", so saving printer_layout from the
    # existing settings screen can never silently wipe a connected
    # Razorpay account. An empty string IS accepted as "disconnect".
    if data.razorpay_key_id is not None:
        settings.razorpay_key_id = data.razorpay_key_id or None
    if data.razorpay_key_secret is not None:
        settings.razorpay_key_secret = data.razorpay_key_secret or None
    if data.razorpay_webhook_secret is not None:
        settings.razorpay_webhook_secret = data.razorpay_webhook_secret or None

    # Onboarding step 3 complete — set-once, never unset (see
    # shop_routes.update_store_settings for the same reasoning).
    if not current_shop.onboarding_billing_done:
        current_shop.onboarding_billing_done = True

    db.commit()
    db.refresh(settings)

    # Same explicit construction as GET — never let key_secret/webhook_secret
    # leak back out, even in the save-confirmation response.
    return BillingSettingsResponse(
        default_gst=settings.default_gst,
        printer_layout=settings.printer_layout,
        razorpay_key_id=settings.razorpay_key_id,
        razorpay_configured=bool(
            settings.razorpay_key_id and settings.razorpay_key_secret and settings.razorpay_webhook_secret
        ),
    )