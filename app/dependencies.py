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


def _validate_shop_session(request: Request, token: str, db: Session) -> Shop:
    """
    Shared steps 1-5 (JWT, shop exists, ACTIVE status, workspace version,
    device binding) — everything EXCEPT the subscription check, which is
    deliberately factored out into get_current_shop() below. Extracted so
    get_current_shop() and get_current_shop_no_subscription() can't drift
    out of sync on the security-relevant parts (device binding especially)
    the way two independent copies inevitably would over time.
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

    return shop


def get_current_shop(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Shop:
    """
    Validates the bearer token and returns the active Shop, requiring an
    existing active/trial, unexpired subscription (see
    _validate_shop_session for steps 1-5; this adds step 6).

    Deliberately still a hard requirement, not a soft Base-tier fallback:
    a shop with no subscription at all gets no app access whatsoever —
    this is the existing, intentional product behavior (confirmed
    2026-08-01: no free-forever Base-tier access; Base only exists as a
    tier DISTINCTION from Premium once a shop has SOME subscription, paid
    or trial or the free base_monthly plan — see subscription_pricing
    /Plan.price_paise == 0 for that "free but still a real subscription
    row" path). A shop must go through create-order (even for the free
    Base plan) or start-trial to get in.

    IMPORTANT: this is why the subscription-purchase endpoints
    themselves (GET /subscription/plans, validate-coupon, create-order,
    verify-payment, start-trial) must NOT depend on this function — a
    brand-new shop with zero subscription rows would 403 here before
    ever reaching the code that lets it obtain one, a chicken-and-egg
    lockout. Those five routes depend on get_current_shop_no_subscription
    instead, which runs the same steps 1-5 but skips step 6.
    """
    shop = _validate_shop_session(request, token, db)

    # ── 6. Subscription check ─────────────────────────────────────────────────
    subscription = (
        db.query(Subscription)
        .filter(Subscription.shop_id == shop.id)
        .order_by(Subscription.expiry_date.desc())
        .first()
    )

    if not subscription:
        raise HTTPException(status_code=403, detail="No active subscription")
    # "trial" is a genuine usable-access status, equivalent to "active" for
    # gating purposes — see Phase 4 of the onboarding/subscription plan.
    # This check used to be `!= "active"` only, which would have silently
    # locked every trialing shop out of the entire app the moment the
    # trial feature shipped, since get_current_shop() gates every
    # authenticated endpoint, not just the tier-gated ones added in
    # Phase 3. Caught here before that ever reached production.
    if subscription.status not in ("active", "trial"):
        raise HTTPException(status_code=403, detail="Subscription inactive")
    if subscription.expiry_date < utc_now():
        raise HTTPException(status_code=403, detail="Subscription expired")

    return shop


def get_current_shop_no_subscription(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Shop:
    """
    Same as get_current_shop() (JWT, shop exists, ACTIVE status,
    workspace version, device binding — the real security checks) but
    WITHOUT requiring an existing subscription. Use this, never
    get_current_shop, for the handful of routes a shop must be able to
    call BEFORE it has any subscription at all: GET /subscription/plans,
    validate-coupon, create-order, verify-payment, start-trial.

    Does not skip device binding — unlike the older get_current_shop_id()
    below, which was already a lighter-weight option but drops device
    validation entirely, not safe to use for endpoints that create real
    financial orders.
    """
    return _validate_shop_session(request, token, db)


def require_premium_tier(
    current_shop: Shop = Depends(get_current_shop),
    db: Session = Depends(get_db),
) -> Shop:
    """
    Second-layer gate for Premium-only features (GST reports, profit
    reports, AI insights). Runs AFTER get_current_shop() has already
    confirmed the shop has some active/trial subscription — this only
    adds the tier check on top.

    This is the actual security boundary for tier-gating: a modified
    client cannot be trusted to self-enforce a UI-only lock, so every
    Premium-only route must depend on this function (not just
    get_current_shop) rather than relying on the Android app hiding the
    entry point.
    """
    subscription = (
        db.query(Subscription)
        .filter(Subscription.shop_id == current_shop.id)
        .order_by(Subscription.expiry_date.desc())
        .first()
    )

    # get_current_shop() already guarantees a subscription exists and is
    # active/trial and unexpired by this point, but re-check defensively
    # rather than assume — this function must be safe to depend on
    # directly in future routes even if someone forgets to also chain
    # get_current_shop() explicitly (FastAPI resolves the Depends(...)
    # default above regardless, but the intent should be explicit here).
    if not subscription or subscription.tier != "premium":
        raise HTTPException(
            status_code=403,
            detail={
                "error": "PREMIUM_REQUIRED",
                "message": "This feature requires a Premium subscription.",
            },
        )

    return current_shop


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
