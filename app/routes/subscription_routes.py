import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import math
from app.util.time_utils import utc_now, utc_to_epoch_ms

from app.database import get_db
from app.dependencies import get_current_shop, get_current_shop_no_subscription, require_admin
from app.models.subscription import Subscription
from app.models.order import Order
from app.models.coupon import Coupon

from app.models.shop import Shop
from app.services.email_service import send_subscription_email
from app.services.audit_log_service import log_event
from app.services.subscription_entitlement_service import (
    is_trial_offerable, resolve_entitlement_state, apply_transition,
)
from app.models.plan import Plan
from app.schemas.subscription_payment_schema import AdminCreateCouponRequest, AdminCouponOut

router = APIRouter(prefix="/subscription", tags=["Subscription"])
logger = logging.getLogger(__name__)


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
            # No live subscription at all → trial is offerable purely
            # based on has_used_trial. See is_trial_offerable below for
            # why the app must read THIS field instead of just negating
            # has_used_trial itself (that was the bug: the trial card
            # kept showing for a shop already on a paid Base plan).
            "is_trial_offerable": is_trial_offerable(current_shop.has_used_trial, None),
        }

    # Ceil so 23h-left reads as 1 day (not 0/'expired') — off-by-a-day fix.
    remaining_days = math.ceil((sub.expiry_date - utc_now()).total_seconds() / 86400)

    # Single shared classifier — replaces a hand-rolled "expired if
    # remaining_days<=0 OR status=='expired'" check that used to live
    # here as its own copy of the same rule. resolve_entitlement_state
    # already covers both cases this used to special-case by hand: a
    # time-based expiry (expiry_date has passed, regardless of whether
    # the 24h sweep has flipped sub.status yet) and an explicit status
    # override (e.g. admin_refund_order setting status="expired" without
    # touching expiry_date) — both fall out of the same expiry_date-first
    # check inside resolve_entitlement_state.
    state = resolve_entitlement_state(sub)
    if state == "expired":
        reported_status = "expired"
    elif state == "trialing":
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
        # The app must use THIS to decide whether to show the trial
        # card/button — never `not has_used_trial` alone. False whenever
        # the shop has a live active_base/active_premium subscription,
        # closing the "trial card shown while already on paid Base" bug.
        "is_trial_offerable": is_trial_offerable(current_shop.has_used_trial, sub),
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

    # 🔍 Get shop (NEW)
    shop = db.query(Shop).filter(Shop.id == shop_id).first()

    if not shop:
        return {"error": "Shop not found"}

    # Routed through apply_transition() instead of writing plan/tier/
    # dates/status directly — this used to be its own separate copy of
    # the same "grant a subscription" logic every other path (start-
    # trial, activate_order) now shares. Always a "fresh" grant (full
    # duration from now), matching this endpoint's pre-existing
    # behavior — an admin-activate is a manual override, not expected to
    # respect a Base shop's remaining days the way a real upgrade would.
    sub = db.query(Subscription).filter(Subscription.shop_id == shop_id).first()
    synthetic_plan = Plan(plan_code=plan, tier=tier, duration_days=duration, price_paise=0, name=plan)
    sub = apply_transition(db, sub, shop_id, synthetic_plan, "fresh")
    expiry = sub.expiry_date

    db.commit()

    log_event(db, shop_id, "admin_activated", f"plan={plan} tier={tier}")

    # ================= EMAIL (NEW) =================
    try:
        send_subscription_email(shop, plan, expiry)
        logger.info("Subscription activation email sent to shop_id=%s", shop_id)
    except Exception as e:
        logger.error("Subscription activation email failed for shop_id=%s: %s", shop_id, e)

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
    # Re-derive status from the shared classifier now that expiry_date
    # has moved into the future, instead of a local copy of the same
    # "was expired, now isn't" rule — resolve_entitlement_state's
    # explicit-status-override check (see subscription_entitlement_
    # service) also means this correctly un-sticks a refund-expired
    # subscription, not just a time-expired one.
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


# ── Coupon management ────────────────────────────────────────────────────
# No admin endpoint existed for this until now — Plan rows are auto-seeded
# on every restart (see main.py _seed_default_plans), but Coupon has no
# equivalent seeding, and until this endpoint the only way to add one was
# a raw INSERT against the coupons table. discount_type/discount_value/
# valid_from/valid_until/max_uses/max_uses_per_shop map 1:1 onto the
# Coupon model fields that subscription_pricing_service.validate_coupon_for_shop
# actually checks — see that function for the exact validation semantics
# each field drives (percentage vs flat, global vs per-shop cap, etc.).

def _parse_optional_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date/time format: {value!r} — use ISO format, e.g. '2026-12-31' or '2026-12-31T23:59:59'",
        )


@router.post("/admin/coupons", dependencies=[Depends(require_admin)])
def admin_create_coupon(body: AdminCreateCouponRequest, db: Session = Depends(get_db)):
    if body.discount_type not in ("percentage", "flat"):
        raise HTTPException(status_code=400, detail="discount_type must be 'percentage' or 'flat'")

    code = body.code.strip().upper()
    existing = db.query(Coupon).filter(Coupon.code == code).first()
    if existing:
        raise HTTPException(status_code=400, detail="A coupon with this code already exists")

    coupon = Coupon(
        code=code,
        discount_type=body.discount_type,
        discount_value=body.discount_value,
        valid_from=_parse_optional_datetime(body.valid_from),
        valid_until=_parse_optional_datetime(body.valid_until),
        max_uses=body.max_uses,
        max_uses_per_shop=body.max_uses_per_shop,
        is_active=True,
    )
    db.add(coupon)
    db.commit()
    db.refresh(coupon)

    log_event(db, None, "admin_coupon_created", f"code={code} discount_type={body.discount_type} discount_value={body.discount_value}")

    return {"message": f"Coupon {code} created", "id": coupon.id}


@router.get("/admin/coupons", response_model=list[AdminCouponOut], dependencies=[Depends(require_admin)])
def admin_list_coupons(db: Session = Depends(get_db)):
    coupons = db.query(Coupon).order_by(Coupon.id.desc()).all()
    return [
        AdminCouponOut(
            id=c.id,
            code=c.code,
            discount_type=c.discount_type,
            discount_value=c.discount_value,
            valid_from=c.valid_from.isoformat() if c.valid_from else None,
            valid_until=c.valid_until.isoformat() if c.valid_until else None,
            max_uses=c.max_uses,
            times_used=c.times_used,
            max_uses_per_shop=c.max_uses_per_shop,
            is_active=c.is_active,
        )
        for c in coupons
    ]


@router.post("/admin/coupons/{coupon_id}/deactivate", dependencies=[Depends(require_admin)])
def admin_deactivate_coupon(coupon_id: int, db: Session = Depends(get_db)):
    coupon = db.query(Coupon).filter(Coupon.id == coupon_id).first()
    if not coupon:
        raise HTTPException(status_code=404, detail="Coupon not found")

    coupon.is_active = False
    db.commit()

    log_event(db, None, "admin_coupon_deactivated", f"code={coupon.code}")

    return {"message": f"Coupon {coupon.code} deactivated"}