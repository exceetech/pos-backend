from app.models.inventory import Inventory
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.models.shop import Shop
from app.models.global_products import GlobalProduct
from app.models.shop_products import ShopProduct
from app.schemas.product_schema import (
    AddProductRequest, HsnVerificationResponse,
    VariantListResponse, ProductNameVerifyResponse,
    ShopProductSyncRequest, ShopProductSyncResponse,
    GlobalProductRegisterRequest, GlobalProductRegisterResponse,
)
from app.models.global_hsn import GlobalHSN
from app.models.global_product_variant import GlobalProductVariant
from app.dependencies import get_current_shop
from app.utils import normalize_name, normalize_variant

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

    variant = data.variant_name.strip() if data.variant_name and data.variant_name.strip() else None
    unit = (data.unit or "piece").lower().strip()

    existing = db.query(ShopProduct).filter(
        ShopProduct.shop_id == current_shop.id,
        ShopProduct.global_product_id == global_product.id,
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
            "is_active": existing.is_active,
            "is_purchased": existing.is_purchased,
            "is_tax_inclusive": existing.is_tax_inclusive
        }
    }


# ================= ADD PRODUCT =================
def get_or_create_global_product(db: Session, normalized: str, shop_id: int) -> GlobalProduct:
    """
    Race-safe get-or-create for a GlobalProduct by its (unique) name.

    global_products.name is UNIQUE, so a plain check-then-insert can 500
    when two requests create the same new name at once. This guards the
    insert with a SAVEPOINT and, on the unique-constraint race, re-fetches
    the row the other request created — guaranteeing exactly one row per
    normalized name (which is what keeps the Android catalog id→name map
    unambiguous).
    """
    gp = db.query(GlobalProduct).filter(GlobalProduct.name == normalized).first()
    if gp is not None:
        return gp
    try:
        with db.begin_nested():
            gp = GlobalProduct(
                name=normalized, is_verified=False, created_by_shop_id=shop_id
            )
            db.add(gp)
            db.flush()
        return gp
    except IntegrityError:
        # Lost the insert race — the winning row should now be visible.
        gp = db.query(GlobalProduct).filter(GlobalProduct.name == normalized).first()
        if gp is None:
            # Extremely unlikely (an IntegrityError implies a committed
            # conflicting row), but never return None to callers that
            # immediately dereference gp.id.
            raise HTTPException(status_code=409, detail="Could not resolve product row")
        return gp


def _apply_variant_fields(v, data, unit_clean: str) -> bool:
    """
    Apply the statutory fields the caller provided onto a
    GlobalProductVariant. Returns True if any stored value actually
    changed. Rules: strings applied only when non-blank, tax fields
    applied when not None (so an explicit 0 sticks), unit only when the
    row still holds the "unit" default.
    """
    changed = False

    def _set(attr, newval):
        nonlocal changed
        if newval is not None and getattr(v, attr) != newval:
            setattr(v, attr, newval)
            changed = True

    if unit_clean != "unit" and (not v.unit or v.unit == "unit"):
        _set("unit", unit_clean)
    if data.hsn_code and data.hsn_code.strip():
        _set("hsn_code", data.hsn_code.strip())
    if data.hsn_description and data.hsn_description.strip():
        _set("hsn_description", data.hsn_description.strip())
    if data.official_uqc and data.official_uqc.strip():
        _set("official_uqc", data.official_uqc.strip().upper())
    _set("default_gst_rate", data.default_gst_rate)
    _set("cgst_percentage", data.cgst_percentage)
    _set("sgst_percentage", data.sgst_percentage)
    _set("igst_percentage", data.igst_percentage)
    _set("cess_rate", data.cess_rate)
    return changed


@router.post("/add-to-shop")
def add_to_shop(
    data: AddProductRequest,
    db: Session = Depends(get_db),
    current_shop: Shop = Depends(get_current_shop)
):
    normalized = normalize_name(data.name)

    global_product = get_or_create_global_product(db, normalized, current_shop.id)

    variant = data.variant_name.strip() if data.variant_name and data.variant_name.strip() else None
    unit = (data.unit or "piece").lower().strip()

    existing = db.query(ShopProduct).filter(
        ShopProduct.shop_id == current_shop.id,
        ShopProduct.global_product_id == global_product.id,
        (
            ShopProduct.variant_name.is_(None)
            if variant is None
            else ShopProduct.variant_name == variant
        )
    ).first()

    # =========================================================
    # 🔁 EXISTING PRODUCT (RESTORE / UPDATE / CONVERT)
    # =========================================================
    if existing:

        existing.price = data.price
        existing.is_active = True
        existing.is_purchased = data.is_purchased
        existing.is_tax_inclusive = data.is_tax_inclusive
        existing.hsn_code = data.hsn_code or existing.hsn_code
        existing.default_gst_rate = data.default_gst_rate or 0.0
        existing.cgst_percentage = data.cgst_percentage or 0.0
        existing.sgst_percentage = data.sgst_percentage or 0.0
        existing.igst_percentage = data.igst_percentage or 0.0
        existing.official_uqc = (data.official_uqc or "").strip().upper() or None
        existing.hsn_description = data.hsn_description or None
        existing.cess_rate = data.cess_rate or 0.0

        db.commit()
        db.refresh(existing)

        inventory = db.query(Inventory).filter(
            Inventory.product_id == existing.id,
            Inventory.shop_id == current_shop.id
        ).first()

        # 🔥 VALIDATION
        if data.track_inventory and data.initial_stock and data.cost_price is None:
            raise HTTPException(400, "Cost price required")

        # ================= INVENTORY LOGIC =================
        if data.track_inventory:
            if inventory:
                inventory.is_active = True
                # If converted or restored with fresh stock, reset the stock
                # rather than mixing old phantom manual stock with new purchased stock.
                if data.initial_stock is not None:
                    inventory.current_stock = data.initial_stock
                    inventory.average_cost = data.cost_price or 0.0
            else:
                new_inventory = Inventory(
                    product_id=existing.id,
                    shop_id=current_shop.id,
                    current_stock=data.initial_stock or 0.0,
                    average_cost=data.cost_price or 0.0,
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
    # NEW PRODUCT
    # =========================================================
    new_product = ShopProduct(
        shop_id=current_shop.id,
        global_product_id=global_product.id,
        variant_name=variant,
        unit=unit,
        price=data.price,
        is_active=True,
        is_purchased=data.is_purchased,
        is_tax_inclusive=data.is_tax_inclusive,
        hsn_code=data.hsn_code or None,
        default_gst_rate=data.default_gst_rate or 0.0,
        cgst_percentage=data.cgst_percentage or 0.0,
        sgst_percentage=data.sgst_percentage or 0.0,
        igst_percentage=data.igst_percentage or 0.0,
        official_uqc=(data.official_uqc or "").strip().upper() or None,
        hsn_description=data.hsn_description or None,
        cess_rate=data.cess_rate or 0.0,
        supply_classification=data.supply_classification or "TAXABLE",
        category=(data.category or "").strip()
    )

    db.add(new_product)
    db.commit()
    db.refresh(new_product)

    if data.track_inventory:
        new_inventory = Inventory(
            product_id=new_product.id,
            shop_id=current_shop.id,
            current_stock=data.initial_stock or 0.0,
            average_cost=data.cost_price or 0.0,
            is_active=True
        )
        db.add(new_inventory)
        db.commit()

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
        ShopProduct.hsn_code,
        ShopProduct.default_gst_rate,
        ShopProduct.cgst_percentage,
        ShopProduct.sgst_percentage,
        ShopProduct.igst_percentage,
        ShopProduct.official_uqc,
        ShopProduct.hsn_description,
        ShopProduct.cess_rate,
        ShopProduct.category,
        ShopProduct.is_active,
        ShopProduct.is_purchased,
        ShopProduct.is_tax_inclusive,
        GlobalProduct.name
    ).join(
        GlobalProduct,
        ShopProduct.global_product_id == GlobalProduct.id
    ).filter(
        ShopProduct.shop_id == current_shop.id
    ).all()

    return [
        {
            "id": r.id,
            "name": r.name,
            "variant": r.variant_name,
            "unit": r.unit,
            "price": r.price,
            "hsn_code": r.hsn_code or "",
            "default_gst_rate": r.default_gst_rate or 0.0,
            "cgst_percentage": r.cgst_percentage or 0.0,
            "sgst_percentage": r.sgst_percentage or 0.0,
            "igst_percentage": r.igst_percentage or 0.0,
            "official_uqc": r.official_uqc,
            "hsn_description": r.hsn_description,
            "cess_rate": r.cess_rate or 0.0,
            "category": r.category or "",
            "is_active": r.is_active,
            "is_purchased": r.is_purchased,
            "is_tax_inclusive": r.is_tax_inclusive
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


# ================= UPDATE PRODUCT FIELDS (PUT /{server_id}) =================

@router.put("/{server_id}")
def update_shop_product(
    server_id: int,
    data: AddProductRequest,
    db: Session = Depends(get_db),
    current_shop: Shop = Depends(get_current_shop)
):
    """
    Update an existing ShopProduct's price, HSN, tax percentages and
    GSTR-1 master fields.  Called by the Android client whenever a
    product that already has a server_id has its fields changed
    (e.g. from EditProductActivity or the purchase add-line dialog).
    """
    product = db.query(ShopProduct).filter(
        ShopProduct.id == server_id,
        ShopProduct.shop_id == current_shop.id
    ).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    product.price            = data.price
    product.is_active        = True
    product.is_purchased     = data.is_purchased
    product.is_tax_inclusive = data.is_tax_inclusive
    product.hsn_code         = data.hsn_code or product.hsn_code
    product.default_gst_rate = data.default_gst_rate or 0.0
    product.cgst_percentage  = data.cgst_percentage or 0.0
    product.sgst_percentage  = data.sgst_percentage or 0.0
    product.igst_percentage  = data.igst_percentage or 0.0
    product.official_uqc     = (data.official_uqc or "").strip().upper() or None
    product.hsn_description  = data.hsn_description or None
    product.cess_rate        = data.cess_rate or 0.0
    product.supply_classification = data.supply_classification or "TAXABLE"
    # ── Category (v40): apply edits; blank leaves the value unchanged. ──
    if (data.category or "").strip():
        product.category = data.category.strip()

    # Reactivate inventory if it exists
    inventory = db.query(Inventory).filter(
        Inventory.product_id == product.id,
        Inventory.shop_id == current_shop.id
    ).first()
    if inventory:
        inventory.is_active = True

    db.commit()
    db.refresh(product)
    return {"message": "Product updated", "product_id": product.id}


# ================= VERIFICATION (FOR ANDROID) =================

@router.get("/verify-hsn/{hsn}", response_model=HsnVerificationResponse)
def verify_hsn(hsn: str, db: Session = Depends(get_db)):
    # Check global registry
    global_hsn = db.query(GlobalHSN).filter(GlobalHSN.hsn_code == hsn).first()
    
    if global_hsn and global_hsn.is_verified:
        return {
            "valid": True,
            "hsn": hsn,
            "description": "HSN Code Verified"
        }
    
    return {
        "valid": False,
        "hsn": hsn,
        "message": "HSN not found in global registry"
    }

@router.get("/verify-name", response_model=ProductNameVerifyResponse)
def verify_product_name(name: str, db: Session = Depends(get_db)):
    normalized = normalize_name(name)
    global_p = db.query(GlobalProduct).filter(GlobalProduct.name == normalized).first()
    
    if global_p and global_p.is_verified:
        return {
            "valid": True,
            "name": name,
            "matched_global_id": global_p.id
        }
    
    return {
        "valid": False,
        "name": name,
        "message": "Product name not verified"
    }

@router.get("/{product_name}/variants", response_model=VariantListResponse)
def get_product_variants_by_name(product_name: str, db: Session = Depends(get_db)):
    normalized = normalize_name(product_name)
    global_p = db.query(GlobalProduct).filter(GlobalProduct.name == normalized).first()
    
    if not global_p:
        return {"product_name": product_name, "variants": []}
        
    variants = db.query(GlobalProductVariant).filter(
        GlobalProductVariant.product_id == global_p.id,
        GlobalProductVariant.is_verified == True,
        GlobalProductVariant.variant_name != ""   # exclude product-level holder
    ).all()

    return {
        "product_name": product_name,
        "variants": [v.variant_name for v in variants]
    }


# ================= GLOBAL PRODUCT REGISTRATION =================
# Called by Android SyncManager after every addProductToShop push.
# Ensures the product, its variant, and its HSN are all present in
# the shared global catalogue (best-effort — never blocks the caller).

@router.post("/global/register", response_model=GlobalProductRegisterResponse)
def register_global_product(
    data: GlobalProductRegisterRequest,
    db: Session = Depends(get_db),
    current_shop: Shop = Depends(get_current_shop)
):
    normalized = normalize_name(data.name)

    # 1. Upsert GlobalProduct (race-safe, single row per name)
    gp = get_or_create_global_product(db, normalized, current_shop.id)

    # 2. Register variant (if provided)
    #
    # This is the SINGLE writer of GlobalProductVariant rows. All other
    # paths (add_to_shop, _upsert_shop_product) touch shop_products only.
    # The existence check keeps the (product_id, variant_name) unique
    # constraint from ever raising IntegrityError.
    # When the product has no named variant we still record a row, using an
    # empty-string variant_name as the PRODUCT-LEVEL statutory holder — so
    # variant-less products carry HSN/GST/UQC for cross-shop autofill just
    # like variant products do.
    variant_key = normalize_variant(data.variant) or ""
    unit_clean = (data.unit or "").strip().lower() or "unit"

    exists_v = db.query(GlobalProductVariant).filter(
        GlobalProductVariant.product_id == gp.id,
        GlobalProductVariant.variant_name == variant_key
    ).first()

    if exists_v is None:
        # Brand-new pending submission — record provenance + the statutory
        # tax fields (never price). Guard the insert with a SAVEPOINT: if
        # another shop registers the same (product_id, variant_name) at the
        # same instant, the unique constraint fires here and we roll back
        # JUST this insert instead of poisoning the whole transaction.
        try:
            with db.begin_nested():
                db.add(GlobalProductVariant(
                    product_id=gp.id,
                    variant_name=variant_key,
                    unit=unit_clean,
                    is_verified=False,
                    created_by_shop_id=current_shop.id,
                    hsn_code=(data.hsn_code.strip() if data.hsn_code else None),
                    hsn_description=(data.hsn_description.strip() if data.hsn_description else None),
                    official_uqc=(data.official_uqc.strip().upper() if data.official_uqc else None),
                    default_gst_rate=data.default_gst_rate or 0.0,
                    cgst_percentage=data.cgst_percentage or 0.0,
                    sgst_percentage=data.sgst_percentage or 0.0,
                    igst_percentage=data.igst_percentage or 0.0,
                    cess_rate=data.cess_rate or 0.0,
                ))
                db.flush()
        except IntegrityError:
            # Another shop won the race and created the row first — that's
            # fine, it already exists globally.
            pass
    elif exists_v.created_by_shop_id == current_shop.id:
        # The OWNING shop is updating its own row. Apply the fields it
        # provided. A non-owner shop's re-sync never reaches here, so it
        # can't overwrite someone else's row or a verified fact.
        changed = _apply_variant_fields(exists_v, data, unit_clean)
        if exists_v.is_verified and changed:
            # The owner corrected data on an already-VERIFIED (canonical)
            # row. Rather than silently changing what other shops rely on,
            # send it back to the admin queue for re-review. Only happens
            # when something actually changed, so normal resyncs don't churn.
            exists_v.is_verified = False

    # 3. Register HSN (if provided)
    if data.hsn_code:
        hsn_clean = data.hsn_code.strip()
        exists_h = db.query(GlobalHSN).filter(
            GlobalHSN.product_id == gp.id,
            GlobalHSN.hsn_code == hsn_clean
        ).first()
        if not exists_h:
            db.add(GlobalHSN(
                product_id=gp.id,
                hsn_code=hsn_clean,
                is_verified=False
            ))

    db.commit()

    return GlobalProductRegisterResponse(
        success=True,
        global_id=gp.id,
        name=normalized,
        variant=data.variant,
        hsn_code=data.hsn_code,
        message="Registered"
    )


# ================= BATCH PRODUCT SYNC =================
# POST /products/sync — bulk upsert for shop products that were
# created offline. Mirrors addProductToShop but accepts a batch,
# writing all GSTR-1 / tax fields so the server table stays in sync
# even when the device reconnects after a long offline period.

def _upsert_shop_product(
    data,          # ShopProductDto
    db: Session,
    shop_id: int
) -> int:
    """Upsert one product and return its server id."""
    normalized = normalize_name(data.name)

    gp = get_or_create_global_product(db, normalized, shop_id)

    variant = data.variant.strip() if data.variant and data.variant.strip() else None
    unit    = (data.unit or "piece").lower().strip()

    existing = db.query(ShopProduct).filter(
        ShopProduct.shop_id         == shop_id,
        ShopProduct.global_product_id == gp.id,
        (
            ShopProduct.variant_name.is_(None)
            if variant is None
            else ShopProduct.variant_name == variant
        )
    ).first()

    combined_gst = (data.cgst_percentage + data.sgst_percentage) or data.igst_percentage

    if existing:
        existing.price            = data.price
        existing.is_active        = data.is_active
        existing.is_purchased     = data.is_purchased
        existing.is_tax_inclusive = data.is_tax_inclusive
        existing.hsn_code         = data.hsn_code or existing.hsn_code
        existing.default_gst_rate = data.default_gst_rate or combined_gst or 0.0
        existing.cgst_percentage  = data.cgst_percentage
        existing.sgst_percentage  = data.sgst_percentage
        existing.igst_percentage  = data.igst_percentage
        existing.official_uqc     = (data.official_uqc or "").strip().upper() or None
        existing.hsn_description  = data.hsn_description or None
        existing.cess_rate        = data.cess_rate or 0.0
        db.flush()
        return existing.id

    sp = ShopProduct(
        shop_id           = shop_id,
        global_product_id = gp.id,
        variant_name      = variant,
        unit              = unit,
        price             = data.price,
        is_active         = data.is_active,
        is_purchased      = data.is_purchased,
        is_tax_inclusive  = data.is_tax_inclusive,
        hsn_code          = data.hsn_code or None,
        default_gst_rate  = data.default_gst_rate or combined_gst or 0.0,
        cgst_percentage   = data.cgst_percentage,
        sgst_percentage   = data.sgst_percentage,
        igst_percentage   = data.igst_percentage,
        official_uqc      = (data.official_uqc or "").strip().upper() or None,
        hsn_description   = data.hsn_description or None,
        cess_rate         = data.cess_rate or 0.0,
        supply_classification = data.supply_classification or "TAXABLE",
        category          = (data.category or "").strip()
    )
    db.add(sp)
    db.flush()
    return sp.id


@router.post("/sync", response_model=ShopProductSyncResponse)
def sync_shop_products(
    payload: ShopProductSyncRequest,
    db: Session = Depends(get_db),
    current_shop: Shop = Depends(get_current_shop)
):
    product_id_map: dict = {}
    success_count = 0

    for item in payload.products:
        try:
            server_id = _upsert_shop_product(item, db, current_shop.id)
            product_id_map[str(item.local_id)] = server_id
            success_count += 1
        except Exception as e:
            # Log and continue — one bad row shouldn't fail the whole batch.
            print(f"[products/sync] failed for local_id={item.local_id}: {e}")

    db.commit()

    return ShopProductSyncResponse(
        success_count=success_count,
        product_id_map=product_id_map,
        message=f"Synced {success_count}/{len(payload.products)} products"
    )
