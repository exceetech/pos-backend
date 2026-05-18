from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from collections import Counter

from app.database import get_db

from app.models.global_products import GlobalProduct
from app.models.shop_products import ShopProduct
from app.models.global_product_variant import GlobalProductVariant
from app.models.global_hsn import GlobalHSN

from app.schemas.global_catalog_schema import VariantResponse, HsnResponse

router = APIRouter(prefix="/global-catalog", tags=["Global Catalog"])


# ============================================================
# 🔥 VERIFY PRODUCT + VARIANT + HSN (SINGLE ENDPOINT)
# ============================================================

@router.put("/verify-product/{product_id}")
def verify_product_complete(
    product_id: int,
    db: Session = Depends(get_db)
):

    # ---------- 1. Verify Product ----------
    product = db.query(GlobalProduct).filter(
        GlobalProduct.id == product_id
    ).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    product.is_verified = True

    # ---------- 2. Get Shop Data ----------
    shop_products = db.query(ShopProduct).filter(
        ShopProduct.global_product_id == product_id
    ).all()

    if not shop_products:
        db.commit()
        return {"message": "Product verified (no shop data)"}

    # ---------- 3. Collect Variants ----------
    variant_set = set()

    for sp in shop_products:
        if sp.variant_name:
            variant_name = sp.variant_name.strip().capitalize()
            unit = sp.unit or "unit"
            variant_set.add((variant_name, unit))

    # ---------- 4. Insert Variants ----------
    variants_added = 0

    for variant_name, unit in variant_set:

        exists = db.query(GlobalProductVariant).filter(
            GlobalProductVariant.product_id == product_id,
            GlobalProductVariant.variant_name == variant_name
        ).first()

        if not exists:
            db.add(GlobalProductVariant(
                product_id=product_id,
                variant_name=variant_name,
                unit=unit,
                is_verified=True
            ))
            variants_added += 1

    # ---------- 5. Collect HSN (SMART: MOST USED) ----------
    hsn_counter = Counter()

    for sp in shop_products:
        if sp.hsn_code:
            hsn_counter[sp.hsn_code.strip()] += 1

    hsn_added = 0

    if hsn_counter:
        # pick most used HSN (best quality data)
        best_hsn = hsn_counter.most_common(1)[0][0]

        exists = db.query(GlobalHSN).filter(
            GlobalHSN.product_id == product_id,
            GlobalHSN.hsn_code == best_hsn
        ).first()

        if not exists:
            db.add(GlobalHSN(
                product_id=product_id,
                hsn_code=best_hsn,
                is_verified=True
            ))
            hsn_added = 1

    # ---------- 6. Commit ----------
    db.commit()

    return {
        "message": "Product, variants and HSN verified",
        "variants_added": variants_added,
        "hsn_added": hsn_added
    }


# ============================================================
# GET VERIFIED VARIANTS (FOR ANDROID)
# ============================================================

@router.get("/products/{product_id}/variants", response_model=list[VariantResponse])
def get_variants(
    product_id: int,
    db: Session = Depends(get_db)
):
    return db.query(GlobalProductVariant).filter(
        GlobalProductVariant.product_id == product_id,
        GlobalProductVariant.is_verified == True
    ).order_by(GlobalProductVariant.variant_name).all()


# ============================================================
# GET VERIFIED HSN (FOR ANDROID AUTOFILL)
# ============================================================

@router.get("/products/{product_id}/hsn", response_model=HsnResponse)
def get_hsn(
    product_id: int,
    db: Session = Depends(get_db)
):
    hsn = db.query(GlobalHSN).filter(
        GlobalHSN.product_id == product_id,
        GlobalHSN.is_verified == True
    ).first()

    if not hsn:
        raise HTTPException(status_code=404, detail="HSN not found")

    return hsn