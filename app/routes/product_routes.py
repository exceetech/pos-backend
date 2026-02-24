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

    global_product = db.query(GlobalProduct)\
        .filter(GlobalProduct.name == normalized)\
        .first()

    # If product doesn't exist globally, create it
    if not global_product:
        global_product = GlobalProduct(
            name=normalized,
            is_verified=False,
            created_by_shop_id=current_shop.id
        )
        db.add(global_product)
        db.commit()
        db.refresh(global_product)

    # Prevent duplicate product for same shop
    existing_shop_product = db.query(ShopProduct).filter(
    ShopProduct.shop_id == current_shop.id,
    ShopProduct.global_product_id == global_product.id
    ).first()

    if existing_shop_product:

        if existing_shop_product.is_active:
            raise HTTPException(status_code=400, detail="Product already added")

        # 🔥 Reactivate instead of error
        existing_shop_product.is_active = True
        existing_shop_product.price = data.price  # update price if needed
        db.commit()

        return {"message": "Product reactivated"}

    shop_product = ShopProduct(
        shop_id=current_shop.id,
        global_product_id=global_product.id,
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
            "price": r.price
        }
        for r in results
    ]


# ================= VERIFY PRODUCT (ADMIN ONLY LATER) =================
@router.put("/verify-product/{product_id}")
def verify_product(product_id: int, db: Session = Depends(get_db)):

    product = db.query(GlobalProduct)\
        .filter(GlobalProduct.id == product_id)\
        .first()

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