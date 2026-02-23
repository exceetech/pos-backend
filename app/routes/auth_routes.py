from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.shop import Shop
from app.schemas.shop_schema import ShopRegister, ShopLogin
from app.security import verify_password
from app.auth import create_access_token

from app.schemas.shop_schema import ShopActivate
from app.security import hash_password

from app.services.email_service import send_registration_emails

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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

    # Send emails
    send_registration_emails(new_shop)

    return {"message": "Registration received. We will contact you soon."}

# ================= LOGIN =================
@router.post("/login")
def login(data: ShopLogin, db: Session = Depends(get_db)):

    shop = db.query(Shop).filter(Shop.email == data.email).first()

    if not shop:
        raise HTTPException(status_code=400, detail="Invalid credentials")

    if shop.status != "ACTIVE":
        raise HTTPException(status_code=403, detail="Account not activated")

    if not verify_password(data.password, shop.password_hash):
        raise HTTPException(status_code=400, detail="Invalid credentials")

    token = create_access_token({"shop_id": shop.id})

    return {
        "access_token": token,
        "token_type": "bearer"
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

    db.commit()

    return {"message": "Shop activated successfully"}