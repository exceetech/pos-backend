from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import shop
from app.models.shop import Shop
from app.schemas.shop_schema import ShopRegister, ShopActivate
from app.security import verify_password, hash_password, create_access_token
from app.security import create_access_token
from app.services.email_service import send_registration_emails
from app.dependencies import get_current_shop

from fastapi import Form

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

    if not shop.password_hash:
        raise HTTPException(status_code=400, detail="Password not set")

    if not verify_password(form_data.password, shop.password_hash):
        raise HTTPException(status_code=400, detail="Invalid credentials")

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