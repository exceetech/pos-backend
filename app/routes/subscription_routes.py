from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import math
from app.util.time_utils import utc_now, utc_to_epoch_ms

from app.database import get_db
from app.dependencies import get_current_shop, get_current_shop_no_subscription, require_admin
from app.models.subscription import Subscription
from app.models.order import Order

from app.models.shop import Shop
from app.services.email_service import send_subscription_email
from app.services.audit_log_service import log_event

router = APIRouter(prefix="/subscription", tags=["Subscription"])


# ================= USER =================
@router.get("/")
def get_subscription(
    db: Session = Depends(get_db),
    # NOT get_current_shop — this endpoint's entire job is to report
    # subscription status, including "there isn't one yet" for a
    # brand-new shop. get_current_shop's step 6 would 403 before ever
    # reaching the `if not sub` branch below, breaking the exact case
    # this endpoint exists to handle gracefully — same chicken-and-egg
    # class of bug as the one fixed on the payment endpoints in
    # dependencies.py.
    current_shop = Depends(get_current_shop_no_subscription)
):
    sub = db.query(Subscription).filter(
        Subscription.shop_id == current_shop.id
    ).first()

    if not sub:
        return {
            "status": "inactive",
            "plan": None,
            "tier": None,
            "remaining_days": 0,
            "expiry_date": None,
            "has_used_trial": current_shop.has_used_trial,
        }

    # Ceil so 23h-left reads as 1 day (not 0/'expired') — off-by-a-day fix.
    remaining_days = math.ceil((sub.expiry_date - utc_now()).total_seconds() / 86400)

    # Two independent ways a subscription can be expired, and this must
    # report "expired" for either: (1) time-based — expiry_date has
    # passed, regardless of whether the 24h expiry cron has gotten
    # around to flipping sub.status yet; (2) an explicit status override
    # — e.g. admin_refund_order sets status="expired" immediately
    # without touching expiry_date, since a refund is "this is no longer
    # valid right now," not "this was never going to expire until a
    # later date." Checking remaining_days alone (as this used to) missed
    # case (2) entirely: a refunded subscription with time nominally left
    # on its original expiry_date would report "active" here even though
    # get_current_shop() correctly 403s every request against it —
    # enforcement was right, the status the user SAW was wrong.
    if remaining_days <= 0 or sub.status == "expired":
        reported_status = "expired"
    elif sub.status == "trial":
        reported_status = "trial"
    else:
        reported_status = "active"

    return {
        "plan": sub.plan,
        # base | premium — the field tier-gated UI and the offline
        # tier-cache (Android, Phase 5) must read; do not infer tier from
        # `plan` string-matching anywhere in the app, see §5.5.
        "tier": sub.tier,
        "expiry_date": sub.expiry_date,
        # UTC instant so the device can render it in the shop timezone.
        "expiry_ms": utc_to_epoch_ms(sub.expiry_date) if sub.expiry_date else None,
        "remaining_days": max(remaining_days, 0),
        "status": reported_status,
        "has_used_trial": current_shop.has_used_trial,
    }


# ================= ADMIN =================

# Security fix: this endpoint had no authentication at all — anyone who
# could reach the API could grant any shop_id a free subscription. Gated
# with the same require_admin shared-secret guard as admin_routes.py /
# admin_catalog_routes.py (see app/dependencies.py for details).
@router.post("/admin/activate", dependencies=[Depends(require_admin)])
def admin_activate_subscription(
    shop_id: int,
    plan: str,
    # Defaults to "premium" to match the Phase 1 backfill assumption for
    # every subscription that existed before tiering shipped (this
    # admin-activate path was, until Phase 2's Razorpay flow lands, the
    # ONLY way a subscription is ever created). Pass tier="base"
    # explicitly for a manual Base-tier grant.
    tier: str = "premium",
    db: Session = Depends(get_db)
):
    # 🔥 Plan duration
    if plan == "monthly":
        duration = 30
    elif plan == "yearly":
        duration = 365
    else:
        return {"error": "Invalid plan"}

    if tier not in ("base", "premium"):
        return {"error": "Invalid tier — must be 'base' or 'premium'"}

    start = utc_now()
    expiry = start + timedelta(days=duration)

    # 🔍 Get shop (NEW)
    shop = db.query(Shop).filter(Shop.id == shop_id).first()

    if not shop:
        return {"error": "Shop not found"}

    # 🔍 Subscription
    sub = db.query(Subscription).filter(
        Subscription.shop_id == shop_id
    ).first()

    if sub:
        sub.plan = plan
        sub.tier = tier
        sub.start_date = start
        sub.expiry_date = expiry
        sub.status = "active"
    else:
        sub = Subscription(
            shop_id=shop_id,
            plan=plan,
            tier=tier,
            start_date=start,
            expiry_date=expiry,
            status="active"
        )
        db.add(sub)

    db.commit()

    log_event(db, shop_id, "admin_activated", f"plan={plan} tier={tier}")

    # ================= EMAIL (NEW) =================
    try:
        send_subscription_email(shop, plan, expiry)
        print("✅ Email sent successfully")
    except Exception as e:
        print("❌ Email failed:", e)

    return {
        "message": f"Activated for shop {shop_id}",
        "expiry_date": expiry
    }


# Admin support path (plan §4.7): manually extend a shop's current
# subscription/trial by N days without requiring payment — for support/
# goodwill cases (a customer had a payment issue, a complaint, etc.).
# Works whether the shop's current subscription is "trial" or "active";
# does not touch has_used_trial, so this is purely a time extension, not
# a way to grant a second trial.
@router.post("/admin/extend", dependencies=[Depends(require_admin)])
def admin_extend_subscription(
    shop_id: int,
    extra_days: int,
    db: Session = Depends(get_db)
):
    if extra_days <= 0:
        return {"error": "extra_days must be positive"}

    sub = db.query(Subscription).filter(Subscription.shop_id == shop_id).first()
    if not sub:
        return {"error": "No subscription found for this shop"}

    # Extend from whichever is later — "now" (if already expired) or the
    # existing expiry (if still running) — so this never accidentally
    # shortens an active period by extending from "now" on a subscription
    # that still has weeks left.
    base = max(sub.expiry_date, utc_now()) if sub.expiry_date else utc_now()
    sub.expiry_date = base + timedelta(days=extra_days)
    if sub.status == "expired":
        sub.status = "trial" if sub.plan == "trial" else "active"

    db.commit()

    log_event(db, shop_id, "admin_extended", f"extra_days={extra_days}")

    return {
        "message": f"Extended shop {shop_id} by {extra_days} day(s)",
        "expiry_date": sub.expiry_date
    }


# Refund path (plan §6.3): Razorpay will generate real refund requests
# from real customers regardless of whether the app exposes a
# self-service cancellation flow — this is the admin-side path that must
# exist even though customers can't trigger it themselves in v1.
# Deliberately simple and explicit: an admin refunding an order is a
# judgment call on their part, not something to try to make "smart"
# (e.g. guessing whether a later order should be left alone) — it always
# immediately expires the shop's current subscription; the admin can
# re-activate/extend afterward via the endpoints above if that was too
# broad for a specific case.
@router.post("/admin/refund-order", dependencies=[Depends(require_admin)])
def admin_refund_order(
    order_id: int,
    db: Session = Depends(get_db)
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        return {"error": "Order not found"}
    if order.status != "paid":
        return {"error": f"Order is '{order.status}', not 'paid' — nothing to refund"}

    order.status = "refunded"

    sub = db.query(Subscription).filter(Subscription.shop_id == order.shop_id).first()
    if sub:
        sub.status = "expired"

    db.commit()

    log_event(db, order.shop_id, "admin_refunded", f"order_id={order_id}", amount_paise=order.amount_paise)

    return {
        "message": f"Order {order_id} marked refunded; shop {order.shop_id}'s subscription expired",
    }