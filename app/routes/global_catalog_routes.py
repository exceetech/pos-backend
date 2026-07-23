from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.database import get_db
from app.dependencies import get_current_shop_id

from app.models.global_products import GlobalProduct
from app.models.global_product_variant import GlobalProductVariant
from app.models.global_hsn import GlobalHSN

from app.schemas.global_catalog_schema import VariantResponse, HsnResponse
from app.utils import normalize_name

router = APIRouter(prefix="/global-catalog", tags=["Global Catalog"])


# ============================================================
# VERIFY PRODUCT + VARIANT + HSN — REMOVED (Report 5)
# ============================================================
# Like /products/verify-product (product_routes.py, also removed this
# pass), this endpoint had NO authentication whatsoever — not even a valid
# shop login token — and let anyone mark a global product, ALL of its
# variants, and an HSN code as verified in one call, fabricating tax/HSN
# data from whichever shop happened to submit it into the shared catalog
# every shop's autofill reads from. The real, properly-gated workflow is
# admin_catalog_routes.py (PUT /admin/catalog/variants/{id}/verify),
# guarded by the X-Admin-Token shared secret. Confirmed unused by the
# Android app before removing.


# ============================================================
# GET VERIFIED VARIANTS (FOR ANDROID)
# ============================================================

@router.get("/products/{product_id}/variants", response_model=list[VariantResponse])
def get_variants(
    product_id: int,
    db: Session = Depends(get_db),
    # Lightweight token-only auth: a read-only catalog lookup shouldn't be
    # gated on active subscription / device binding. Just needs the shop id
    # for the "verified OR mine" filter.
    current_shop_id: int = Depends(get_current_shop_id),
):
    # Verified globally OR still-unverified but submitted by THIS shop.
    return db.query(GlobalProductVariant).filter(
        GlobalProductVariant.product_id == product_id,
        or_(
            GlobalProductVariant.is_verified == True,
            GlobalProductVariant.created_by_shop_id == current_shop_id,
        ),
    ).order_by(GlobalProductVariant.variant_name).all()


@router.get("/products/variants-by-name", response_model=list[VariantResponse])
def get_variants_by_name(
    name: str,
    db: Session = Depends(get_db),
    current_shop_id: int = Depends(get_current_shop_id),
):
    """
    One-shot variant fetch by product NAME. Merges across ALL global
    product rows sharing the (normalized) name — so legacy duplicate
    products are handled server-side in a single call instead of the
    client looping per id. Same "verified OR mine" visibility.
    """
    normalized = normalize_name(name)
    product_ids = [
        pid for (pid,) in db.query(GlobalProduct.id)
        .filter(GlobalProduct.name == normalized).all()
    ]
    if not product_ids:
        return []
    return db.query(GlobalProductVariant).filter(
        GlobalProductVariant.product_id.in_(product_ids),
        or_(
            GlobalProductVariant.is_verified == True,
            GlobalProductVariant.created_by_shop_id == current_shop_id,
        ),
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