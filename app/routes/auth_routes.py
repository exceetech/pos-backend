from app.schemas.SaveTokenRequest import SaveTokenRequest
from app.schemas.VerifyPasswordRequest import VerifyPasswordRequest
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Form
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

    existing = db.query(Shop).filter(Shop.email == shop.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    new_shop = Shop(
        shop_name=shop.shop_name,
        owner_name=shop.owner_name,
        email=shop.email,
        phone=shop.phone,
        status="PENDING"
    )

    db.add(new_shop)
    db.commit()
    db.refresh(new_shop)

    # Send emails
    send_registration_emails(new_shop)

    return {"message": "Registration received. We will contact you soon."}


# ================= LOGIN =================

@router.post("/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):

    shop = db.query(Shop).filter(Shop.email == form_data.username).first()

    if not shop:
        raise HTTPException(status_code=400, detail="Invalid credentials")

    if shop.status != "ACTIVE":
        raise HTTPException(status_code=403, detail="Account not activated")

    from app.security import hash_password

    # check if password stored is NOT hashed
    if not shop.password_hash.startswith("$2b$"):

        # first login after upgrade
        if form_data.password != shop.password_hash:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # convert plaintext password to hash
        shop.password_hash = hash_password(shop.password_hash)
        db.commit()

    else:
        if not verify_password(form_data.password, shop.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token(data={"shop_id": shop.id})

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "is_first_login": shop.is_first_login
    }


# ================= ACTIVATE SHOP =================
@router.post("/activate-shop")
def activate_shop(data: ShopActivate, db: Session = Depends(get_db)):

    shop = db.query(Shop).filter(Shop.email == data.email).first()

    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    if shop.status == "ACTIVE":
        raise HTTPException(status_code=400, detail="Shop already active")

    shop.password_hash = hash_password(data.temporary_password)
    shop.status = "ACTIVE"
    shop.is_first_login = True

    db.commit()

    return {"message": "Shop activated successfully"}


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
    shop.reset_otp_expiry = datetime.utcnow() + timedelta(minutes=1)
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

    if shop.reset_otp_expiry < datetime.utcnow():
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
    reset_token = create_access_token(
    data={
        "shop_id": shop.id,
        "scope": "password_reset"
    }
)

    return {
        "otp_verified": True,
        "email": email,
        "access_token": reset_token,
        "token_type": "bearer"
    }


# ================= GENERATE RESET TOKEN =================
@router.post("/generate-reset-token")
def generate_reset_token(email: str, db: Session = Depends(get_db)):

    email = email.strip().lower()

    shop = db.query(Shop).filter(Shop.email == email).first()

    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    reset_token = create_access_token(
    data={
        "shop_id": shop.id,
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

    db.commit()

    return {"message": "Password reset successful"}