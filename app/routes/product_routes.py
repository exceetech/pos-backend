from app.models.inventory import Inventory
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

    # ================= GLOBAL PRODUCT =================
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

    # ================= NORMALIZE =================
    variant = data.variant_name.strip() if data.variant_name else None
    unit = (data.unit or "unit").lower().strip()

    # ================= CHECK EXISTING =================
    existing = db.query(ShopProduct).filter(
        ShopProduct.shop_id == current_shop.id,
        ShopProduct.global_product_id == global_product.id,
        ShopProduct.unit == unit,
        (
            ShopProduct.variant_name.is_(None)
            if variant is None
            else ShopProduct.variant_name == variant
        )
    ).first()

    # =========================================================
    # 🔁 EXISTING PRODUCT
    # =========================================================
    if existing:

        existing.price = data.price
        existing.is_active = True

        db.commit()
        db.refresh(existing)

        # 🔥 INVENTORY FIX
        inventory = db.query(Inventory).filter(
            Inventory.product_id == existing.id,
            Inventory.shop_id == current_shop.id
        ).first()

        if inventory:
            inventory.is_active = True

            # 🔥 ADD STOCK IF PROVIDED
            if data.initial_stock and data.initial_stock > 0:
                inventory.current_stock += data.initial_stock

            db.commit()

        else:
            # 🔥 CREATE NEW INVENTORY IF MISSING
            if data.initial_stock and data.initial_stock > 0:
                new_inventory = Inventory(
                    product_id=existing.id,
                    shop_id=current_shop.id,
                    current_stock=data.initial_stock,
                    average_cost=data.cost_price or 0,
                    is_active=True
                )
                db.add(new_inventory)
                db.commit()

    # =========================================================
    # 🆕 NEW PRODUCT
    # =========================================================
    new_product = ShopProduct(
        shop_id=current_shop.id,
        global_product_id=global_product.id,
        variant_name=variant,
        unit=unit,
        price=data.price,
        is_active=True
    )

    db.add(new_product)
    db.commit()
    db.refresh(new_product)

    return {
        "message": "Product added successfully",
        "product_id": new_product.id  # 🔥 VERY IMPORTANT
    }

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

    # 🔥 deactivate product

    product.is_active = False

    # 🔥 ALSO deactivate inventory

    inventory = db.query(Inventory).filter(

        Inventory.product_id == product_id,

        Inventory.shop_id == current_shop.id

    ).first()

    if inventory:

        inventory.is_active = False

    db.commit()

    return {"message": "Product deactivated"} 