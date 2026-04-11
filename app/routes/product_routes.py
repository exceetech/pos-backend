from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.database import get_db
from app.models.shop import Shop
from app.models.global_products import GlobalProduct
from app.models.shop_products import ShopProduct
from app.schemas.product_schema import AddProductRequest
from app.dependencies import get_current_shop
from app.utils import normalize_name

router = APIRouter(prefix="/products", tags=["Products"])


# ================= CATALOG =================
@router.get("/catalog")
def get_catalog(
    db: Session = Depends(get_db),
    current_shop: Shop = Depends(get_current_shop)
):
    return db.query(GlobalProduct).filter(
        or_(
            GlobalProduct.is_verified == True,
            GlobalProduct.created_by_shop_id == current_shop.id
        )
    ).all()


# ================= ADD PRODUCT TO SHOP =================
@router.post("/add-to-shop")
def add_to_shop(
    data: AddProductRequest,
    db: Session = Depends(get_db),
    current_shop: Shop = Depends(get_current_shop)
):
    normalized = normalize_name(data.name)

    # 🔹 Get or create global product
    global_product = db.query(GlobalProduct).filter(
        GlobalProduct.name == normalized
    ).first()

    if not global_product:
        global_product = GlobalProduct(
            name=normalized,
            is_verified=False,
            created_by_shop_id=current_shop.id
        )
        db.add(global_product)
        db.commit()
        db.refresh(global_product)

    # 🔥 IMPORTANT: normalize variant + unit
    variant = data.variant_name.strip() if data.variant_name else None
    unit = (data.unit or "unit").lower().strip()

    
    existing_shop_product = db.query(ShopProduct).filter(
        ShopProduct.shop_id == current_shop.id,
        ShopProduct.global_product_id == global_product.id,
        ShopProduct.unit == unit,
        (
            ShopProduct.variant_name.is_(None)
            if variant is None
            else ShopProduct.variant_name == variant
        )
    ).first()

    if existing_shop_product:

        # ✅ If already active → UPDATE price (NO ERROR)
        if existing_shop_product.is_active:
            existing_shop_product.price = data.price
            db.commit()
            return {"message": "Variant price updated"}

        # ♻️ Reactivate
        existing_shop_product.is_active = True
        existing_shop_product.price = data.price
        db.commit()

        return {"message": "Variant reactivated"}

    # ✅ Create new variant
    shop_product = ShopProduct(
        shop_id=current_shop.id,
        global_product_id=global_product.id,
        variant_name=variant,
        unit=unit,
        price=data.price
    )

    db.add(shop_product)
    db.commit()

    return {"message": "Product added successfully"}


# ================= GET MY PRODUCTS =================
@router.get("/my-products")
def get_my_products(
    db: Session = Depends(get_db),
    current_shop: Shop = Depends(get_current_shop)
):

    results = db.query(
        ShopProduct.id,
        ShopProduct.price,
        ShopProduct.variant_name,
        ShopProduct.unit,
        GlobalProduct.name
    ).join(
        GlobalProduct,
        ShopProduct.global_product_id == GlobalProduct.id
    ).filter(
        ShopProduct.shop_id == current_shop.id,
        ShopProduct.is_active == True
    ).all()

    return [
        {
            "id": r.id,
            "name": r.name,
            "variant": r.variant_name,   # ✅ match Android model
            "unit": r.unit,
            "price": r.price
        }
        for r in results
    ]


# ================= VERIFY PRODUCT =================
@router.put("/verify-product/{product_id}")
def verify_product(product_id: int, db: Session = Depends(get_db)):

    product = db.query(GlobalProduct).filter(
        GlobalProduct.id == product_id
    ).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    product.is_verified = True
    db.commit()

    return {"message": "Product verified successfully"}


# ================= DEACTIVATE PRODUCT =================
@router.put("/deactivate/{product_id}")
def deactivate_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_shop: Shop = Depends(get_current_shop)
):
    product = db.query(ShopProduct).filter(
        ShopProduct.id == product_id,
        ShopProduct.shop_id == current_shop.id
    ).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    product.is_active = False
    db.commit()

    return {"message": "Product deactivated"}