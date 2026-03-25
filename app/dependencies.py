from fastapi import Depends, HTTPException, Request
from datetime import datetime
from sqlalchemy.orm import Session

from app.database import get_db
from app.security import verify_token
from app.models.shop import Shop
from app.models.subscription import Subscription

from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_shop(
    request: Request,  # 🔥 ADD THIS
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    shop_id = verify_token(token)

    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=401, detail="Shop not found")

    # =====================================================
    # 🔒 DEVICE VALIDATION (NEW)
    # =====================================================

    device_id = request.headers.get("device_id")

    if not device_id:
        raise HTTPException(status_code=400, detail="Device ID missing")

    if not shop.device_id:
        # Safety: bind device if somehow not set
        shop.device_id = device_id
        db.commit()

    elif shop.device_id != device_id:
        raise HTTPException(
            status_code=403,
            detail="Access denied: different device detected"
        )

    # =====================================================
    # 💳 SUBSCRIPTION CHECK (YOUR EXISTING LOGIC)
    # =====================================================

    subscription = (
        db.query(Subscription)
        .filter(Subscription.shop_id == shop_id)
        .order_by(Subscription.expiry_date.desc())
        .first()
    )

    if not subscription:
        raise HTTPException(status_code=403, detail="No active subscription")

    if subscription.status != "active":
        raise HTTPException(status_code=403, detail="Subscription inactive")

    if subscription.expiry_date < datetime.utcnow():
        raise HTTPException(status_code=403, detail="Subscription expired")

    return shop