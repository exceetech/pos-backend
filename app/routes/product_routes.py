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


# ================= CHECK PRODUCT (NEW 🔥) =================
@router.post("/check")
def check_product(
    data: AddProductRequest,
    db: Session = Depends(get_db),
    current_shop: Shop = Depends(get_current_shop)
):
    normalized = normalize_name(data.name)

    global_product = db.query(GlobalProduct).filter(
        GlobalProduct.name == normalized
    ).first()

    if not global_product:
        return {"exists": False}

    variant = data.variant_name.strip() if data.variant_name else None
    unit = (data.unit or "piece").lower().strip()

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

    if not existing:
        return {"exists": False}

    inventory = db.query(Inventory).filter(
        Inventory.product_id == existing.id,
        Inventory.shop_id == current_shop.id
    ).first()

    return {
        "exists": True,
        "product": {
            "id": existing.id,
            "price": existing.price,
            "variant": existing.variant_name,
            "unit": existing.unit,
            "has_inventory": inventory is not None,
            "stock": inventory.current_stock if inventory else 0,
            "avg_cost": inventory.average_cost if inventory else 0,
            "is_active": existing.is_active
        }
    }


# ================= ADD PRODUCT =================
@router.post("/add-to-shop")
def add_to_shop(
    data: AddProductRequest,
    db: Session = Depends(get_db),
    current_shop: Shop = Depends(get_current_shop)
):
    normalized = normalize_name(data.name)

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

    variant = data.variant_name.strip() if data.variant_name else None
    unit = (data.unit or "piece").lower().strip()

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
    # 🔁 EXISTING PRODUCT (RESTORE / UPDATE)
    # =========================================================
    if existing:

        existing.price = data.price
        existing.is_active = True

        db.commit()
        db.refresh(existing)

        inventory = db.query(Inventory).filter(
            Inventory.product_id == existing.id,
            Inventory.shop_id == current_shop.id
        ).first()

        # 🔥 VALIDATION
        if data.track_inventory and data.initial_stock and not data.cost_price:
            raise HTTPException(400, "Cost price required")

        # ================= INVENTORY LOGIC =================
        if data.track_inventory:

            if inventory:
                inventory.is_active = True

                # if data.initial_stock and data.initial_stock > 0:

                #     old_stocak = inventory.current_stock
                #     old_avg = inventory.average_cost

                #     new_stock = old_stock + data.initial_stock

                #     new_avg = (
                #         ((old_stock * old_avg) + (data.initial_stock * (data.cost_price or old_avg)))
                #         / new_stock
                #     )

                #     inventory.current_stock = new_stock
                #     inventory.average_cost = new_avg

            else:
                new_inventory = Inventory(
                    product_id=existing.id,
                    shop_id=current_shop.id,
                    current_stock=data.initial_stock,
                    average_cost=data.cost_price or 0,
                    is_active=True
                )
                db.add(new_inventory)

        else:
            # 🔥 TURN OFF INVENTORY
            if inventory:
                inventory.is_active = False

        db.commit()

        return {
            "message": "Product restored",
            "product_id": existing.id
        }

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
        "product_id": new_product.id
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
            "variant": r.variant_name,
            "unit": r.unit,
            "price": r.price
        }
        for r in results
    ]


# ================= DEACTIVATE =================
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
        raise HTTPException(404, "Product not found")

    product.is_active = False

    inventory = db.query(Inventory).filter(
        Inventory.product_id == product_id,
        Inventory.shop_id == current_shop.id
    ).first()

    if inventory:
        inventory.is_active = False

    db.commit()

    return {"message": "Product deactivated"}