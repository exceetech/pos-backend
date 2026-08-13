from app.schemas.SaveTokenRequest import SaveTokenRequest
from app.schemas.VerifyPasswordRequest import VerifyPasswordRequest
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Form, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.shop import Shop
from app.schemas.shop_schema import ShopRegister, ForgotPasswordRequest
from app.security import verify_password, hash_password, create_access_token
from app.dependencies import get_current_shop, get_current_shop_no_subscription, require_admin
from app.services.app_config_service import get_config, get_config_bool
import secrets
import hashlib
from datetime import timedelta
from app.util.time_utils import utc_now
from app.services.email_service import send_otp_email

from fastapi import Header
from app.security import decode_token
from app.schemas.security_schema import ChangePasswordRequest


router = APIRouter(prefix="/auth", tags=["Authentication"])


# ================= REGISTER =================
@router.post("/register")
def register(shop: ShopRegister, db: Session = Depends(get_db)):

    email = shop.email.strip().lower()

    existing = db.query(Shop).filter(Shop.email == email).first()
    if existing:
        # A verified/active account already owns this email -> block.
        if existing.status != "PENDING":
            raise HTTPException(status_code=400, detail="Email already registered")

        # Otherwise the account was never verified (registration abandoned
        # before OTP). Treat re-register as idempotent: refresh the details
        # and re-issue a fresh OTP instead of returning 400.
        existing.shop_name = shop.shop_name
        existing.owner_name = shop.owner_name
        existing.phone = shop.phone
        target_shop = existing
    else:
        target_shop = Shop(
            shop_name=shop.shop_name,
            owner_name=shop.owner_name,
            email=email,
            phone=shop.phone,
            status="PENDING"
        )
        db.add(target_shop)

    db.commit()

    # 🔥 REUSE FORGOT PASSWORD FLOW
    otp = str(secrets.randbelow(900000) + 100000)
    otp_hash = hashlib.sha256(otp.encode()).hexdigest()

    target_shop.reset_otp_hash = otp_hash
    target_shop.reset_otp_expiry = utc_now() + timedelta(minutes=5)
    target_shop.reset_otp_attempts = 0

    db.commit()

    send_otp_email(target_shop, otp)

    return {"message": "OTP sent to email"}


# ================= LOGIN =================

@router.post("/login")
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):

    # 🔥 GET DEVICE ID FROM HEADER
    device_id = request.headers.get("device_id")

    if not device_id:
        raise HTTPException(status_code=400, detail="Device ID missing")

    shop = db.query(Shop).filter(Shop.email == form_data.username).first()

    if not shop:
        raise HTTPException(status_code=400, detail="Invalid credentials")

    if shop.status != "ACTIVE":
        raise HTTPException(status_code=403, detail="Account not activated")

    from app.security import hash_password

    # 🔐 PASSWORD CHECK (UNCHANGED)
    if not shop.password_hash.startswith("$2b$"):

        if form_data.password != shop.password_hash:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        shop.password_hash = hash_password(shop.password_hash)
        db.commit()

    else:
        if not verify_password(form_data.password, shop.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")

    # =====================================================
    # 🔥 DEVICE LOCK LOGIC (NEW)
    # =====================================================

    # First login → bind device
    if not shop.device_id:
        shop.device_id = device_id
        db.commit()

    # Already bound → check device
    elif shop.device_id != device_id:
        raise HTTPException(
            status_code=403,
            detail="This account is already logged in on another device"
        )

    # =====================================================

    access_token = create_access_token(data={
        "shop_id":           shop.id,
        "workspace_version": shop.workspace_version or 1,
    })

    if shop.is_first_login:
        shop.is_first_login = False
        db.commit()

    return {
        "access_token":   access_token,
        "token_type":     "bearer",
        "is_first_login": shop.is_first_login,
        "shop_id":        shop.id,
    }

# # ================= ACTIVATE SHOP =================
# @router.post("/activate-shop")
# def activate_shop(data: ShopActivate, db: Session = Depends(get_db)):

#     shop = db.query(Shop).filter(Shop.email == data.email).first()

#     if not shop:
#         raise HTTPException(status_code=404, detail="Shop not found")

#     if shop.status == "ACTIVE":
#         raise HTTPException(status_code=400, detail="Shop already active")

#     shop.password_hash = hash_password(data.temporary_password)
#     shop.status = "ACTIVE"
#     shop.is_first_login = True

#     db.commit()

#     return {"message": "Shop activated successfully"}


# ================= GET MY PROFILE =================
@router.get("/me")
def get_my_profile(
    db: Session = Depends(get_db),
    # NOT get_current_shop — this is the endpoint Splash/MainActivity use
    # for the onboarding routing gate (plan §2.2), which must work
    # BEFORE a shop has any subscription at all (onboarding step 1 IS
    # obtaining a subscription). get_current_shop's subscription
    # requirement would 403 here during exactly the window this endpoint
    # needs to report onboarding progress for. Same chicken-and-egg class
    # of fix as get_current_shop_no_subscription's other call sites.
    current_shop: Shop = Depends(get_current_shop_no_subscription)
):
    return {
        "shop_name": current_shop.shop_name,
        "owner_name": current_shop.owner_name,
        "email": current_shop.email,
        "status": current_shop.status,
        # Onboarding routing gate fields (plan §2.2/§2.6) — Splash/
        # MainActivity/ChangePasswordActivity all read
        # onboarding_completed_at to decide whether to route into
        # OnboardingActivity instead of Dashboard. The per-step flags let
        # OnboardingActivity resume at the right step instead of
        # restarting after an interruption.
        "onboarding_completed_at": current_shop.onboarding_completed_at,
        "onboarding_subscription_done": current_shop.onboarding_subscription_done,
        "onboarding_shop_info_done": current_shop.onboarding_shop_info_done,
        "onboarding_billing_done": current_shop.onboarding_billing_done,
        "onboarding_terms_done": current_shop.onboarding_terms_done,
        # Kill switch (plan §6.6) — every routing gate must check this
        # BEFORE redirecting into OnboardingActivity, so onboarding
        # enforcement can be turned off server-side (e.g. a bug found
        # post-launch) without shipping a new APK.
        "onboarding_enforcement_enabled": get_config_bool(db, "onboarding_enforcement_enabled"),
    }


# ================= ONBOARDING =================

@router.post("/accept-terms")
def accept_terms(
    current_shop: Shop = Depends(get_current_shop),
    db: Session = Depends(get_db),
):
    """
    Onboarding step 4. Uses the FULL get_current_shop (subscription
    required) — by the time a shop reaches the terms step, step 1
    (subscription) is already done, since the wizard's fixed order is
    Subscription → Shop info → Billing → Terms (plan §2.1).
    """
    required_version = get_config(db, "required_terms_version")

    current_shop.terms_accepted_at = utc_now()
    current_shop.terms_version = required_version
    if not current_shop.onboarding_terms_done:
        current_shop.onboarding_terms_done = True

    db.commit()

    return {"message": "Terms accepted", "terms_version": required_version}


@router.post("/complete-onboarding")
def complete_onboarding(
    current_shop: Shop = Depends(get_current_shop),
    db: Session = Depends(get_db),
):
    """
    Final onboarding step. Deliberately re-verifies all four sub-steps
    server-side rather than trusting the app to have honestly walked
    through the wizard (plan §2.5) — a modified client calling this
    directly with steps skipped must not be able to stamp
    onboarding_completed_at.
    """
    missing = [
        name for name, done in [
            ("subscription", current_shop.onboarding_subscription_done),
            ("shop_info", current_shop.onboarding_shop_info_done),
            ("billing", current_shop.onboarding_billing_done),
            ("terms", current_shop.onboarding_terms_done),
        ] if not done
    ]

    if missing:
        raise HTTPException(
            status_code=400,
            detail={"error": "ONBOARDING_INCOMPLETE", "missing_steps": missing},
        )

    if not current_shop.onboarding_completed_at:
        current_shop.onboarding_completed_at = utc_now()
        db.commit()

    return {"message": "Onboarding complete", "onboarding_completed_at": current_shop.onboarding_completed_at}

# ================= CHANGE PASSWORD =================
@router.post("/change-password")
def change_password(
    new_password: str = Form(...),
    current_shop: Shop = Depends(get_current_shop),
    db: Session = Depends(get_db)
):
    # Server-side floor (Sync/Security audit): this is a Form field, not a
    # Pydantic model, so it doesn't get the min_length=6 constraint added to
    # ChangePasswordRequest — enforce it explicitly here too, so the
    # first-login password-change path can't be used to set an empty or
    # 1-character password.
    if len(new_password) < 6:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 6 characters"
        )

    current_shop.password_hash = hash_password(new_password)
    current_shop.is_first_login = False
    db.commit()

    return {"message": "Password updated successfully"}

# ================= VERIFY PASSWORD =================
@router.post("/verify-password")
def verify_password_route(
    data: VerifyPasswordRequest,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):

    if not verify_password(data.password, current_shop.password_hash):
        raise HTTPException(status_code=401, detail="Invalid password")

    return {"message": "Verified"}

# ================= SAVE FCM TOKEN =================

@router.post("/save-token")
def save_token(
    data: SaveTokenRequest,
    db: Session = Depends(get_db),
    shop = Depends(get_current_shop)
):

    print("FCM TOKEN RECEIVED:", data.token)

    shop.fcm_token = data.token
    db.commit()

    return {"message": "Token saved"}

# ================= FORGOT PASSWORD =================
@router.post("/forgot-password")
def forgot_password(
    request: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)):

    email = request.email

    shop = db.query(Shop).filter(Shop.email == email).first()

    if not shop:
        return {"message": "Please input registered email"}

    otp = str(secrets.randbelow(900000) + 100000)
    otp_hash = hashlib.sha256(otp.encode()).hexdigest()

    shop.reset_otp_hash = otp_hash
    shop.reset_otp_expiry = utc_now() + timedelta(minutes=1)
    shop.reset_otp_attempts = 0

    db.commit()

    background_tasks.add_task(send_otp_email, shop, otp)

    return {"message": "If registered, OTP has been sent."}


# ================= VERIFY OTP =================

@router.post("/verify-otp")
def verify_otp(email: str, otp: str, db: Session = Depends(get_db)):

    shop = db.query(Shop).filter(Shop.email == email).first()

    if not shop or not shop.reset_otp_hash:
        raise HTTPException(status_code=400, detail="Invalid request")

    if shop.reset_otp_expiry < utc_now():
        raise HTTPException(status_code=410, detail="OTP expired")

    if shop.reset_otp_attempts >= 3:
        raise HTTPException(status_code=429, detail="Too many attempts")

    otp_hash = hashlib.sha256(otp.encode()).hexdigest()

    if otp_hash != shop.reset_otp_hash:
        shop.reset_otp_attempts += 1
        db.commit()
        db.refresh(shop)
        raise HTTPException(status_code=401, detail="Invalid OTP")

    # OTP correct
    shop.reset_otp_hash = None
    shop.reset_otp_expiry = None
    shop.reset_otp_attempts = 0
    db.commit()
    # Report 5 fix: this used to omit expires_delta entirely, so the token
    # silently fell back to the standard 24-HOUR session lifetime
    # (ACCESS_TOKEN_EXPIRE_HOURS in security.py) instead of a short-lived
    # reset window. Matches the 10-minute window already used below /
    # previously in generate-reset-token.
    reset_token = create_access_token(
    data={
        "shop_id": shop.id,
        "scope": "password_reset"
    },
    expires_delta=timedelta(minutes=10)
)

    return {
        "otp_verified": True,
        "email": email,
        "access_token": reset_token,
        "token_type": "bearer"
    }


# ================= GENERATE RESET TOKEN (ADMIN) =================
# Re-gated behind require_admin (ADMIN_API_TOKEN / X-Admin-Token — same
# shared-secret guard used by admin_catalog_routes.py, admin_routes.py, and
# POST /subscription/admin/activate).
#
# Originally this endpoint accepted just an `email` query parameter — no
# OTP, no password, nothing — and handed back a valid password-reset token
# for that shop. Combined with a since-fixed gap in get_current_shop()
# (it now rejects any token carrying a `scope` claim for non-reset
# endpoints), an unguarded reset token doubled as a full session credential
# everywhere — a complete account-takeover path for anyone who knew a
# registered email address. It is still NOT meant for the Android app to
# call; the app's own reset path is /auth/verify-otp, which requires the
# emailed OTP. This is strictly an admin/support tool now, for cases where
# support needs to issue a reset token without the shop having mailbox
# access (e.g. verifying identity by other means). Do not expose this to
# the client app or call it without ADMIN_API_TOKEN set in production.
@router.post("/generate-reset-token", dependencies=[Depends(require_admin)])
def generate_reset_token(email: str, db: Session = Depends(get_db)):

    email = email.strip().lower()

    shop_row = db.query(Shop).filter(Shop.email == email).first()

    if not shop_row:
        raise HTTPException(status_code=404, detail="Shop not found")

    reset_token = create_access_token(
        data={
            "shop_id": shop_row.id,
            "scope": "password_reset"
        },
        expires_delta=timedelta(minutes=10)
    )

    return {
        "otp_verified": True,
        "access_token": reset_token,
        "token_type": "bearer"
    }


# ================= INVALIDATE TOKEN =================

@router.post("/invalidate-token")
def invalidate_token():
    return {
        "message": "Reset session completed"
    }

# ================= RESET PASSWORD =================
@router.post("/reset-password")
def reset_password(
    data: ChangePasswordRequest,
    authorization: str = Header(...),
    db: Session = Depends(get_db)
):

    token = authorization.replace("Bearer ", "")

    payload = decode_token(token)

    # 🔐 Ensure token is only for reset
    if payload.get("scope") != "password_reset":
        raise HTTPException(status_code=403, detail="Invalid reset token")

    shop_id = payload.get("shop_id")

    shop = db.query(Shop).filter(Shop.id == shop_id).first()

    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    shop.password_hash = hash_password(data.new_password)
    shop.status = "ACTIVE"

    db.commit()

    return {"message": "Password reset successful"}

# ================= RESET DEVICE (ADMIN) =================
# Restored at the user's explicit request, re-gated behind require_admin
# (ADMIN_API_TOKEN / X-Admin-Token — same shared-secret guard used
# elsewhere in this file and by admin_catalog_routes.py / admin_routes.py).
#
# Originally this endpoint took a shop_id path parameter and cleared that
# shop's device lock with NO authentication check of any kind — anyone who
# could reach the API could unbind any shop's device, defeating the
# one-device-per-account protection for the entire app. It also had no
# null-check (an invalid shop_id would 500, not 404) — fixed here too.
@router.post("/reset-device/{shop_id}", dependencies=[Depends(require_admin)])
def reset_device(shop_id: int, db: Session = Depends(get_db)):

    shop_row = db.query(Shop).filter(Shop.id == shop_id).first()

    if not shop_row:
        raise HTTPException(status_code=404, detail="Shop not found")

    shop_row.device_id = None
    db.commit()

    return {"message": "Device reset"}