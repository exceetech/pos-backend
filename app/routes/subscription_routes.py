from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import math
from app.util.time_utils import utc_now, utc_to_epoch_ms

from app.database import get_db
from app.dependencies import get_current_shop, require_admin
from app.models.subscription import Subscription

from app.models.shop import Shop
from app.services.email_service import send_subscription_email

router = APIRouter(prefix="/subscription", tags=["Subscription"])


# ================= USER =================
@router.get("/")
def get_subscription(
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):
    sub = db.query(Subscription).filter(
        Subscription.shop_id == current_shop.id
    ).first()

    if not sub:
        return {
            "status": "inactive",
            "plan": None,
            "remaining_days": 0,
            "expiry_date": None
        }

    # Ceil so 23h-left reads as 1 day (not 0/'expired') — off-by-a-day fix.
    remaining_days = math.ceil((sub.expiry_date - utc_now()).total_seconds() / 86400)

    return {
        "plan": sub.plan,
        "expiry_date": sub.expiry_date,
        # UTC instant so the device can render it in the shop timezone.
        "expiry_ms": utc_to_epoch_ms(sub.expiry_date) if sub.expiry_date else None,
        "remaining_days": max(remaining_days, 0),
        "status": "active" if remaining_days > 0 else "expired"
    }


# ================= ADMIN =================

# Security fix: this endpoint had no authentication at all — anyone who
# could reach the API could grant any shop_id a free subscription. Gated
# with the same require_admin shared-secret guard as admin_routes.py /
# admin_catalog_routes.py (see app/dependencies.py for details).
@router.post("/admin/activate", dependencies=[Depends(require_admin)])
def admin_activate_subscription(
    shop_id: int,
    plan: str,
    db: Session = Depends(get_db)
):
    # 🔥 Plan duration
    if plan == "monthly":
        duration = 30
    elif plan == "yearly":
        duration = 365
    else:
        return {"error": "Invalid plan"}

    start = utc_now()
    expiry = start + timedelta(days=duration)

    # 🔍 Get shop (NEW)
    shop = db.query(Shop).filter(Shop.id == shop_id).first()

    if not shop:
        return {"error": "Shop not found"}

    # 🔍 Subscription
    sub = db.query(Subscription).filter(
        Subscription.shop_id == shop_id
    ).first()

    if sub:
        sub.plan = plan
        sub.start_date = start
        sub.expiry_date = expiry
        sub.status = "active"
    else:
        sub = Subscription(
            shop_id=shop_id,
            plan=plan,
            start_date=start,
            expiry_date=expiry,
            status="active"
        )
        db.add(sub)

    db.commit()

    # ================= EMAIL (NEW) =================
    try:
        send_subscription_email(shop, plan, expiry)
        print("✅ Email sent successfully")
    except Exception as e:
        print("❌ Email failed:", e)

    return {
        "message": f"Activated for shop {shop_id}",
        "expiry_date": expiry
    }