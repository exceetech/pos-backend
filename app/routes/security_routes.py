import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_shop
from app.models.bill import Bill
from app.models.shop import Shop
from app.models.subscription import Subscription
from app.models.shop_products import ShopProduct
from app.models.billing_settings import BillingSettings
from app.schemas.security_schema import ChangePasswordRequest
from app.security import hash_password, create_access_token

router = APIRouter(prefix="/security", tags=["Security"])


# ─────────────────────────────────────────────────────────────────────────────
#  Clear bills (soft-archive, legacy feature — not part of Workspace Rotation)
# ─────────────────────────────────────────────────────────────────────────────

@router.put("/clear-bills")
def clear_bills(
    db: Session = Depends(get_db),
    current_shop: Shop = Depends(get_current_shop)
):
    bills = db.query(Bill).filter(
        Bill.shop_id == current_shop.id,
        Bill.active  == True
    ).all()
    for bill in bills:
        bill.active = False
    db.commit()
    return {"message": "All bills archived successfully"}


# ─────────────────────────────────────────────────────────────────────────────
#  Change password
# ─────────────────────────────────────────────────────────────────────────────

@router.put("/change-password")
def change_password(
    data: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_shop: Shop = Depends(get_current_shop)
):
    current_shop.password_hash = hash_password(data.new_password)
    db.commit()
    return {"message": "Password updated successfully"}


# ─────────────────────────────────────────────────────────────────────────────
#  PUT /security/factory-reset — Workspace Rotation
#
#  Principle:
#    Every factory reset archives the entire current Shop and provisions a
#    brand-new Shop that shares the same login credentials and active
#    subscription.  NO business table (bills, purchases, inventory, credit
#    notes, GST records, etc.) is modified — they remain attached to the
#    archived Shop and can be fully restored by the admin at any time.
#
#  Transaction guarantee:
#    All mutations execute inside a single implicit SQLAlchemy transaction.
#    If anything raises, SQLAlchemy rolls back before returning the error.
# ─────────────────────────────────────────────────────────────────────────────

@router.put("/factory-reset")
def factory_reset(
    db: Session = Depends(get_db),
    current_shop: Shop = Depends(get_current_shop)
):
    # Guard: only ACTIVE shops may reset.
    if current_shop.status != "ACTIVE":
        raise HTTPException(
            status_code=400,
            detail="Only an active workspace can be factory-reset."
        )

    # ── STEP 1: Snapshot original credentials (write-once) ────────────────────
    if not current_shop.original_phone:
        current_shop.original_phone = current_shop.phone
    if not current_shop.original_email:
        current_shop.original_email = current_shop.email

    original_phone = current_shop.original_phone
    original_email = current_shop.original_email
    old_ws_version = current_shop.workspace_version or 1

    # ── STEP 2: Archive the current shop ──────────────────────────────────────
    prefix = f"archived_{int(time.time())}_"
    current_shop.status = "ARCHIVED"
    current_shop.phone  = prefix + (current_shop.phone  or "")
    current_shop.email  = prefix + (current_shop.email  or "")

    # ── STEP 3: Create the new (clean) shop ───────────────────────────────────
    # Only identity + auth credentials are carried over.
    # No products, inventory, bills, customers, or any business data.
    new_shop = Shop(
        shop_name         = current_shop.shop_name,
        owner_name        = current_shop.owner_name,
        phone             = original_phone,
        email             = original_email,
        password_hash     = current_shop.password_hash,
        device_id         = current_shop.device_id,
        fcm_token         = current_shop.fcm_token,
        store_address     = current_shop.store_address,
        store_gstin       = current_shop.store_gstin,
        status            = "ACTIVE",
        is_first_login    = False,
        type              = current_shop.type,
        workspace_version = old_ws_version + 1,
    )
    db.add(new_shop)
    db.flush()   # assigns new_shop.id without committing

    # ── STEP 4: Migrate active subscription ───────────────────────────────────
    active_sub = (
        db.query(Subscription)
        .filter(
            Subscription.shop_id == current_shop.id,
            Subscription.status  == "active",
        )
        .first()
    )
    if active_sub:
        active_sub.shop_id = new_shop.id

    # ── STEP 5: Commit (atomic) ───────────────────────────────────────────────
    db.commit()
    db.refresh(new_shop)

    # ── STEP 6: Return workspace-versioned JWT ────────────────────────────────
    access_token = create_access_token({
        "shop_id":           new_shop.id,
        "workspace_version": new_shop.workspace_version,
    })

    return {
        "message":      "Factory reset completed. New workspace is ready.",
        "access_token": access_token,
        "new_shop_id":  new_shop.id,
    }
