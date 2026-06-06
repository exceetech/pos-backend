import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.shop import Shop
from app.models.subscription import Subscription
from app.firebase_service import send_broadcast

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
#  Broadcast (existing)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/admin/broadcast")
def broadcast_notification(title: str, body: str, db: Session = Depends(get_db)):
    shops  = db.query(Shop).all()
    tokens = [s.fcm_token for s in shops if s.fcm_token]
    send_broadcast(tokens, title, body)
    return {"message": "Notification sent"}


# ─────────────────────────────────────────────────────────────────────────────
#  GET /admin/archived-shops?email=...
#
#  Lists every archived workspace that originally belonged to the given email.
#  The ``email`` column after archiving contains the ``archived_{ts}_`` prefix,
#  so it uniquely identifies *when* each snapshot was taken.
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/admin/archived-shops")
def list_archived_shops(email: str, db: Session = Depends(get_db)):
    shops = (
        db.query(Shop)
        .filter(
            Shop.original_email == email,
            Shop.status         == "ARCHIVED",
        )
        .order_by(Shop.id.desc())
        .all()
    )

    return [
        {
            "shop_id":          s.id,
            "shop_name":        s.shop_name,
            "owner_name":       s.owner_name,
            "archived_email":   s.email,            # contains timestamp prefix
            "original_phone":   s.original_phone,
            "original_email":   s.original_email,
            "workspace_version": s.workspace_version,
            "created_at":       s.created_at.isoformat() if s.created_at else None,
        }
        for s in shops
    ]


# ─────────────────────────────────────────────────────────────────────────────
#  POST /admin/restore-shop/{archived_shop_id}
#
#  Atomically swaps an archived workspace back to ACTIVE.
#
#  Step summary:
#    1. Fetch + validate the archived shop.
#    2. Read original_phone / original_email.
#    3. Find the currently ACTIVE shop for those credentials.
#    4. Archive the active shop (free the unique credentials).
#    5. Copy latest auth fields from the active shop into the archived shop
#       (password, device_id, fcm_token) so the restored workspace uses the
#       most current credentials.
#    6. Restore the archived shop: status=ACTIVE, original creds, +1 version.
#    7. Move subscription to restored shop.
#    8. Commit.
#
#  Result:
#    The next time the user opens the app and the 409 kicks in, they reload
#    into the restored workspace — 100% of historical data intact, zero
#    business-table modifications.
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/admin/restore-shop/{archived_shop_id}")
def restore_shop(archived_shop_id: int, db: Session = Depends(get_db)):

    # ── STEP 1: Validate archived shop ────────────────────────────────────────
    archived_shop = db.query(Shop).filter(Shop.id == archived_shop_id).first()
    if not archived_shop:
        raise HTTPException(status_code=404, detail="Archived shop not found")
    if archived_shop.status != "ARCHIVED":
        raise HTTPException(
            status_code=400,
            detail=f"Shop {archived_shop_id} is not ARCHIVED (status={archived_shop.status})"
        )

    # ── STEP 2: Original credentials ──────────────────────────────────────────
    original_phone = archived_shop.original_phone
    original_email = archived_shop.original_email

    if not original_email:
        raise HTTPException(
            status_code=400,
            detail="Cannot restore: original_email is missing from archived shop."
        )

    # ── STEP 3: Find currently active shop ────────────────────────────────────
    active_shop = (
        db.query(Shop)
        .filter(
            Shop.original_email == original_email,
            Shop.status         == "ACTIVE",
        )
        .first()
    )
    # Fallback: search by restored email if original_email lookup misses
    if not active_shop and original_email:
        active_shop = (
            db.query(Shop)
            .filter(
                Shop.email  == original_email,
                Shop.status == "ACTIVE",
            )
            .first()
        )

    prefix = f"archived_{int(time.time())}_"

    # ── STEP 4 & 5: Archive the active shop + snapshot latest auth ────────────
    latest_password = archived_shop.password_hash
    latest_device   = archived_shop.device_id
    latest_fcm      = archived_shop.fcm_token
    next_version    = (archived_shop.workspace_version or 1)

    if active_shop:
        # Snapshot original credentials of active shop (write-once).
        if not active_shop.original_phone:
            active_shop.original_phone = active_shop.phone
        if not active_shop.original_email:
            active_shop.original_email = active_shop.email

        # Capture the most recent auth state.
        latest_password = active_shop.password_hash or latest_password
        latest_device   = active_shop.device_id   or latest_device
        latest_fcm      = active_shop.fcm_token    or latest_fcm
        next_version    = (active_shop.workspace_version or 1) + 1

        # Archive active shop.
        active_shop.status = "ARCHIVED"
        active_shop.phone  = prefix + (active_shop.phone or "")
        active_shop.email  = prefix + (active_shop.email or "")

        # ── CRITICAL: flush NOW so Postgres sees the renamed email before
        # we write the original email back onto the archived shop below.
        # Without this flush, SQLAlchemy batches both UPDATEs and Postgres
        # raises UniqueViolation on ix_shops_email.
        db.flush()

        # Move subscription away from active shop.
        active_sub = (
            db.query(Subscription)
            .filter(
                Subscription.shop_id == active_shop.id,
                Subscription.status  == "active",
            )
            .first()
        )
        if active_sub:
            active_sub.shop_id = archived_shop_id

    # ── STEP 6: Restore the archived shop ─────────────────────────────────────
    archived_shop.status            = "ACTIVE"
    archived_shop.phone             = original_phone
    archived_shop.email             = original_email
    archived_shop.workspace_version = next_version
    # Use latest credentials so user's current password works.
    archived_shop.password_hash     = latest_password
    archived_shop.device_id         = latest_device
    archived_shop.fcm_token         = latest_fcm

    # ── STEP 7: Ensure subscription points to restored shop ───────────────────
    restored_sub = (
        db.query(Subscription)
        .filter(Subscription.shop_id == archived_shop_id)
        .order_by(Subscription.expiry_date.desc())
        .first()
    )
    if restored_sub:
        restored_sub.status  = "active"
        restored_sub.shop_id = archived_shop_id

    # ── STEP 8: Commit (atomic) ───────────────────────────────────────────────
    db.commit()

    return {
        "message":           "Shop restored successfully.",
        "restored_shop_id":  archived_shop_id,
        "archived_shop_id":  active_shop.id if active_shop else None,
        "workspace_version": next_version,
    }
