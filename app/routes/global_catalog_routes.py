from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from collections import Counter

from app.database import get_db
from app.dependencies import get_current_shop_id

from app.models.global_products import GlobalProduct
from app.models.shop_products import ShopProduct
from app.models.global_product_variant import GlobalProductVariant
from app.models.global_hsn import GlobalHSN

from app.schemas.global_catalog_schema import VariantResponse, HsnResponse
from app.utils import normalize_variant, normalize_name

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

    # ---------- 3. Collect Variants + representative tax data ----------
    # Build one record per normalized variant, carrying the statutory
    # tax fields from the shop products so verified variants ship with a
    # usable autofill payload (not empty).
    variant_meta = {}  # variant_name -> dict(unit, hsn, cgst, sgst, igst, cess)

    for sp in shop_products:
        # Empty-string key = product-level holder for variant-less rows,
        # so variant-less products still get a verified autofill payload.
        vn = normalize_variant(sp.variant_name) or ""
        m = variant_meta.get(vn)
        if m is None:
            variant_meta[vn] = {
                "unit": sp.unit or "unit",
                "hsn":  (sp.hsn_code.strip() if sp.hsn_code else None),
                "hsn_desc": (sp.hsn_description.strip() if sp.hsn_description else None),
                "uqc": (sp.official_uqc.strip().upper() if sp.official_uqc else None),
                "cgst": sp.cgst_percentage or 0.0,
                "sgst": sp.sgst_percentage or 0.0,
                "igst": sp.igst_percentage or 0.0,
                "cess": sp.cess_rate or 0.0,
            }
        else:
            # Backfill any tax field the first-seen row lacked.
            if not m["hsn"] and sp.hsn_code:
                m["hsn"] = sp.hsn_code.strip()
            if not m["hsn_desc"] and sp.hsn_description:
                m["hsn_desc"] = sp.hsn_description.strip()
            if not m["uqc"] and sp.official_uqc:
                m["uqc"] = sp.official_uqc.strip().upper()
            if not m["cgst"] and (sp.cgst_percentage or 0.0) > 0:
                m["cgst"] = sp.cgst_percentage
            if not m["sgst"] and (sp.sgst_percentage or 0.0) > 0:
                m["sgst"] = sp.sgst_percentage
            if not m["igst"] and (sp.igst_percentage or 0.0) > 0:
                m["igst"] = sp.igst_percentage
            if not m["cess"] and (sp.cess_rate or 0.0) > 0:
                m["cess"] = sp.cess_rate

    # ---------- 4. Upsert + verify Variants (with tax autofill) ----------
    variants_added = 0

    for variant_name, m in variant_meta.items():
        total_gst = m["igst"] if m["igst"] > 0 else (m["cgst"] + m["sgst"])

        exists = db.query(GlobalProductVariant).filter(
            GlobalProductVariant.product_id == product_id,
            GlobalProductVariant.variant_name == variant_name
        ).first()

        if exists is None:
            db.add(GlobalProductVariant(
                product_id=product_id,
                variant_name=variant_name,
                unit=m["unit"],
                is_verified=True,
                hsn_code=m["hsn"],
                hsn_description=m["hsn_desc"],
                official_uqc=m["uqc"],
                default_gst_rate=total_gst,
                cgst_percentage=m["cgst"],
                sgst_percentage=m["sgst"],
                igst_percentage=m["igst"],
                cess_rate=m["cess"],
            ))
            variants_added += 1
        else:
            # Verify the already-queued row and fill only the empty
            # tax fields (never clobber existing data).
            exists.is_verified = True
            if m["unit"] and m["unit"] != "unit" and (not exists.unit or exists.unit == "unit"):
                exists.unit = m["unit"]
            if not exists.hsn_code and m["hsn"]:
                exists.hsn_code = m["hsn"]
            if not exists.hsn_description and m["hsn_desc"]:
                exists.hsn_description = m["hsn_desc"]
            if not exists.official_uqc and m["uqc"]:
                exists.official_uqc = m["uqc"]
            if not exists.cgst_percentage and m["cgst"]:
                exists.cgst_percentage = m["cgst"]
            if not exists.sgst_percentage and m["sgst"]:
                exists.sgst_percentage = m["sgst"]
            if not exists.igst_percentage and m["igst"]:
                exists.igst_percentage = m["igst"]
            if not exists.cess_rate and m["cess"]:
                exists.cess_rate = m["cess"]
            if not exists.default_gst_rate and total_gst:
                exists.default_gst_rate = total_gst

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