from app.schemas.SaveTokenRequest import SaveTokenRequest
from app.schemas.VerifyPasswordRequest import VerifyPasswordRequest
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Form, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import shop
from app.models.shop import Shop
from app.schemas.shop_schema import ShopRegister, ShopActivate, ForgotPasswordRequest
from app.security import verify_password, hash_password, create_access_token
from app.security import create_access_token
from app.services.email_service import send_registration_emails
from app.dependencies import get_current_shop
import secrets
import hashlib
from datetime import datetime, timedelta
from app.util.time_utils import utc_now
from app.services.email_service import send_otp_email

from fastapi import Header
from app.security import decode_token
from app.schemas.security_schema import ChangePasswordRequest

from app.security import decode_token, hash_password
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
def get_my_profile(current_shop: Shop = Depends(get_current_shop)):
    return {
        "shop_name": current_shop.shop_name,
        "owner_name": current_shop.owner_name,
        "email": current_shop.email,
        "status": current_shop.status
    }

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


# ================= GENERATE RESET TOKEN — REMOVED (Report 5) =================
# This endpoint used to accept just an `email` query parameter — no OTP, no
# password, nothing — and hand back a valid password-reset token for that
# shop. Combined with the missing `scope` check that get_current_shop() used
# to have (also fixed in this pass), that token worked as a full session
# credential everywhere, not just for /auth/reset-password: a full account
# takeover for anyone who knew a registered email address. Confirmed unused
# by the Android app (no caller anywhere in the client) before removing —
# the only legitimate path to a reset token is /auth/verify-otp, which
# actually requires the emailed OTP.


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

# ================= RESET DEVICE (ADMIN) — REMOVED (Report 5) =================
# This endpoint took a shop_id path parameter and cleared that shop's device
# lock with NO authentication check of any kind — anyone who could reach the
# API could unbind any shop's device, defeating the one-device-per-account
# protection for the entire app. It also had no null-check (an invalid
# shop_id would 500, not 404). Confirmed unused by the Android app. Device
# lock is currently permanent-until-support-intervenes by design; if a real
# "admin resets a customer's device" tool is needed later, it needs a proper
# admin-auth mechanism first — this codebase doesn't have one yet (see the
# same gap in admin_routes.py's other endpoints, flagged separately).