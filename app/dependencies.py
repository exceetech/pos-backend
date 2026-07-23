import os
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request
from datetime import datetime
from app.util.time_utils import utc_now
from sqlalchemy.orm import Session

from app.database import get_db
from app.security import verify_token_full
from app.models.shop import Shop
from app.models.subscription import Subscription

from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def require_admin(x_admin_token: Optional[str] = Header(None)) -> None:
    """
    Shared-secret guard for admin-tier endpoints (catalog review, shop
    broadcast/archive/restore, subscription activation).

    - If the ADMIN_API_TOKEN env var is NOT set, the endpoint stays open —
      this keeps local/dev setups usable out of the box.
    - Once ADMIN_API_TOKEN is set, callers must send a matching
      `X-Admin-Token` header or they're rejected.

    Originally defined only in admin_catalog_routes.py and applied to that
    router. admin_routes.py (broadcast / archived-shops / restore-shop) and
    POST /subscription/admin/activate had NO guard at all — not even the
    optional env-var one — so anyone who could reach the API could
    broadcast to every device, enumerate archived-shop PII by email,
    swap a live shop out from under its owner via restore-shop, or grant
    any shop_id a free subscription, all with zero authentication. Moved
    here so every admin-tier router can share the same gate.
    """
    expected = os.getenv("ADMIN_API_TOKEN")
    if expected and x_admin_token != expected:
        raise HTTPException(status_code=401, detail="Admin authorization required")


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

    # Report 5 fix (critical): tokens issued for the password-reset flow
    # (/auth/verify-otp, /auth/generate-reset-token) carry scope="password_reset"
    # and are meant to be usable for exactly one thing — POST /auth/reset-password.
    # This function used to never check `scope` at all, so a reset token was a
    # fully valid session token for every other authenticated endpoint in the
    # app (bills, inventory, customers, everything) for its entire lifetime.
    # A normal login token never sets `scope`, so anything with one set here
    # is, by definition, not a login session token.
    if payload.get("scope") is not None:
        raise HTTPException(
            status_code=401,
            detail="This token cannot be used for this action",
        )

    # ── 2. Shop exists ────────────────────────────────────────────────────────
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=401, detail="Shop not found")

    # ── 3. Shop must be ACTIVE ────────────────────────────────────────────────
    if shop.status != "ACTIVE":
        # If the shop is ARCHIVED, and the token has a workspace_version,
        # it means the workspace was rotated or restored. We must throw 409
        # so the client knows to wipe its local database.
        if shop.status == "ARCHIVED" and jwt_ws_version is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "error":   "WORKSPACE_CHANGED",
                    "message": "Your workspace has been replaced or restored. "
                               "Please reload the app to continue.",
                }
            )
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
    if subscription.expiry_date < utc_now():
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
    # Report 5 fix: same scope guard as get_current_shop() above — a
    # password-reset-scoped token must not authenticate anything else.
    if payload.get("scope") is not None:
        raise HTTPException(
            status_code=401,
            detail="This token cannot be used for this action",
        )
    return int(payload["shop_id"])
