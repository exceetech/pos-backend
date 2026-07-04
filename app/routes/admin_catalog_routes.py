"""
Admin — Global Catalog review.

Lets an admin review the queue of shop-submitted (unverified) product
variants and explicitly verify/correct them. These endpoints operate
STRICTLY on the global catalog (global_product_variants). They never
read or mutate shop_products / inventory — that isolation is what keeps
each shop's billing prices untouched.
"""
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.global_products import GlobalProduct
from app.models.global_product_variant import GlobalProductVariant
from app.utils import normalize_variant


def require_admin(x_admin_token: Optional[str] = Header(None)):
    """
    Optional shared-secret guard for the catalog-admin endpoints.

    - If the ADMIN_API_TOKEN env var is NOT set, the endpoints stay open
      (consistent with the rest of the admin_routes surface).
    - Once ADMIN_API_TOKEN is set, callers must send a matching
      `X-Admin-Token` header or they're rejected.

    This keeps the endpoints usable out of the box while letting you lock
    them down simply by setting the env var.
    """
    expected = os.getenv("ADMIN_API_TOKEN")
    if expected and x_admin_token != expected:
        raise HTTPException(status_code=401, detail="Admin authorization required")


router = APIRouter(
    prefix="/admin/catalog",
    tags=["admin-catalog"],
    dependencies=[Depends(require_admin)],
)


class UnverifiedVariantOut(BaseModel):
    id: int
    product_id: int
    product_name: str
    variant_name: str
    # Human-readable label for the queue: the variant name, or
    # "(no variant)" for the product-level "" holder row. Display-only —
    # never send this back as variant_name to the edit endpoint.
    label: str = ""
    unit: str
    hsn_code: Optional[str] = None
    hsn_description: Optional[str] = None
    official_uqc: Optional[str] = None
    default_gst_rate: float = 0.0
    cgst_percentage: float = 0.0
    sgst_percentage: float = 0.0
    igst_percentage: float = 0.0
    cess_rate: float = 0.0
    created_by_shop_id: Optional[int] = None


class EditVariantRequest(BaseModel):
    # All optional — only the fields you actually include in the JSON body
    # are changed; anything omitted (None) is left untouched. This is an
    # EXPLICIT edit, kept separate from verify so approving can never
    # rewrite data by accident.
    variant_name: Optional[str] = None
    hsn_code: Optional[str] = None
    hsn_description: Optional[str] = None
    official_uqc: Optional[str] = None
    default_gst_rate: Optional[float] = None
    cgst_percentage: Optional[float] = None
    sgst_percentage: Optional[float] = None
    igst_percentage: Optional[float] = None
    cess_rate: Optional[float] = None


@router.get("/unverified", response_model=list[UnverifiedVariantOut])
def list_unverified_variants(db: Session = Depends(get_db)):
    rows = (
        db.query(GlobalProductVariant, GlobalProduct.name)
        .join(GlobalProduct, GlobalProductVariant.product_id == GlobalProduct.id)
        .filter(GlobalProductVariant.is_verified == False)  # noqa: E712
        .order_by(GlobalProduct.name, GlobalProductVariant.variant_name)
        .all()
    )
    return [
        UnverifiedVariantOut(
            id=v.id,
            product_id=v.product_id,
            product_name=name,
            variant_name=v.variant_name,
            label=(v.variant_name or "(no variant)"),
            unit=v.unit,
            hsn_code=v.hsn_code,
            hsn_description=v.hsn_description,
            official_uqc=v.official_uqc,
            default_gst_rate=v.default_gst_rate or 0.0,
            cgst_percentage=v.cgst_percentage or 0.0,
            sgst_percentage=v.sgst_percentage or 0.0,
            igst_percentage=v.igst_percentage or 0.0,
            cess_rate=v.cess_rate or 0.0,
            created_by_shop_id=v.created_by_shop_id,
        )
        for v, name in rows
    ]


@router.put("/variants/{variant_id}/verify")
def verify_variant(
    variant_id: int,
    db: Session = Depends(get_db),
):
    """
    Approve a queued variant AS-IS.

    This ONLY flips is_verified (on the variant and its parent product).
    It deliberately takes no request body and never rewrites the
    variant's name / HSN / tax fields — so hitting it from Swagger
    (whose example body is full of "string"/0 placeholders) can never
    corrupt the real data. To change a value, use the edit endpoint.
    """
    variant = (
        db.query(GlobalProductVariant)
        .filter(GlobalProductVariant.id == variant_id)
        .first()
    )
    if variant is None:
        raise HTTPException(404, "Variant not found")

    variant.is_verified = True

    # A verified variant implies its parent product is legitimate — verify
    # it too. Other shops' catalog filters on GlobalProduct.is_verified, so
    # without this the product never surfaces for them and the variant
    # dropdown stays empty even though the variant itself is verified.
    product = (
        db.query(GlobalProduct)
        .filter(GlobalProduct.id == variant.product_id)
        .first()
    )
    if product is not None and not product.is_verified:
        product.is_verified = True

    db.commit()
    db.refresh(variant)

    return {
        "success": True,
        "id": variant.id,
        "is_verified": True,
        "product_verified": True,
    }


@router.patch("/variants/{variant_id}")
def edit_variant(
    variant_id: int,
    data: EditVariantRequest,
    db: Session = Depends(get_db),
):
    """
    Explicitly correct a variant's fields. Only the fields present in the
    JSON body are changed; omit a field to leave it as-is. Does NOT change
    is_verified — verifying is a separate action.

    Note: this endpoint intentionally writes whatever you send, so when
    using Swagger, delete the fields you don't want to change from the
    example body (otherwise its "string"/0 placeholders get written).
    """
    variant = (
        db.query(GlobalProductVariant)
        .filter(GlobalProductVariant.id == variant_id)
        .first()
    )
    if variant is None:
        raise HTTPException(404, "Variant not found")

    if data.variant_name is not None:
        cleaned = normalize_variant(data.variant_name)
        if not cleaned:
            raise HTTPException(422, "variant_name cannot be blank")
        # Guard the (product_id, variant_name) unique constraint.
        clash = (
            db.query(GlobalProductVariant)
            .filter(
                GlobalProductVariant.product_id == variant.product_id,
                GlobalProductVariant.variant_name == cleaned,
                GlobalProductVariant.id != variant.id,
            )
            .first()
        )
        if clash is not None:
            raise HTTPException(
                409, f"A variant '{cleaned}' already exists for this product"
            )
        variant.variant_name = cleaned

    if data.hsn_code is not None:
        variant.hsn_code = data.hsn_code.strip() or None
    if data.hsn_description is not None:
        variant.hsn_description = data.hsn_description.strip() or None
    if data.official_uqc is not None:
        variant.official_uqc = data.official_uqc.strip().upper() or None
    if data.default_gst_rate is not None:
        variant.default_gst_rate = data.default_gst_rate
    if data.cgst_percentage is not None:
        variant.cgst_percentage = data.cgst_percentage
    if data.sgst_percentage is not None:
        variant.sgst_percentage = data.sgst_percentage
    if data.igst_percentage is not None:
        variant.igst_percentage = data.igst_percentage
    if data.cess_rate is not None:
        variant.cess_rate = data.cess_rate

    db.commit()
    db.refresh(variant)

    return {
        "success": True,
        "id": variant.id,
        "variant_name": variant.variant_name,
        "hsn_code": variant.hsn_code,
        "hsn_description": variant.hsn_description,
        "official_uqc": variant.official_uqc,
        "default_gst_rate": variant.default_gst_rate,
        "cgst_percentage": variant.cgst_percentage,
        "sgst_percentage": variant.sgst_percentage,
        "igst_percentage": variant.igst_percentage,
        "cess_rate": variant.cess_rate,
        "is_verified": variant.is_verified,
    }
