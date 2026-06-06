from fastapi import Depends, HTTPException, Request
from datetime import datetime
from sqlalchemy.orm import Session

from app.database import get_db
from app.security import verify_token_full
from app.models.shop import Shop
from app.models.subscription import Subscription

from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_shop(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Shop:
    """
    Validates the bearer token and returns the active Shop.

    Checks (in order):
      1. JWT is valid and contains shop_id.
      2. Shop exists in the database.
      3. Shop status is ACTIVE (not PENDING or ARCHIVED).
      4. workspace_version in JWT matches DB — if the JWT carries a version
         and it differs from the current DB value the workspace was rotated
         or restored while this token was live → 409 WORKSPACE_CHANGED.
      5. Device ID header matches bound device.
      6. Active, non-expired subscription exists.
    """

    # ── 1. Decode JWT ─────────────────────────────────────────────────────────
    payload = verify_token_full(token)
    shop_id        = int(payload["shop_id"])
    jwt_ws_version = payload.get("workspace_version")   # None for old tokens

    # ── 2. Shop exists ────────────────────────────────────────────────────────
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=401, detail="Shop not found")

    # ── 3. Shop must be ACTIVE ────────────────────────────────────────────────
    if shop.status != "ACTIVE":
        raise HTTPException(
            status_code=401,
            detail="Account is not active. Please contact support."
        )

    # ── 4. Workspace version check ────────────────────────────────────────────
    # Only enforced when the JWT contains a version (tokens issued after
    # the Workspace Rotation rollout).  Old tokens without the field are
    # allowed through for backwards compatibility.
    if jwt_ws_version is not None:
        db_version = shop.workspace_version or 1
        if int(jwt_ws_version) != db_version:
            raise HTTPException(
                status_code=409,
                detail={
                    "error":   "WORKSPACE_CHANGED",
                    "message": "Your workspace has been replaced or restored. "
                               "Please reload the app to continue.",
                }
            )

    # ── 5. Device validation ──────────────────────────────────────────────────
    device_id = request.headers.get("device_id")
    if not device_id:
        raise HTTPException(status_code=400, detail="Device ID missing")

    if not shop.device_id:
        shop.device_id = device_id
        db.commit()
    elif shop.device_id != device_id:
        raise HTTPException(
            status_code=403,
            detail="Access denied: different device detected"
        )

    # ── 6. Subscription check ─────────────────────────────────────────────────
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


def get_current_shop_id(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> int:
    """
    Lightweight version used by routes that only need the shop_id.
    Skips device and subscription validation intentionally.
    """
    payload = verify_token_full(token)
    return int(payload["shop_id"])
