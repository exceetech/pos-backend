"""
Razorpay-backed subscription purchase flow — plan selection, coupon
validation, order creation, and payment verification.

TRUST BOUNDARY (read before touching this file): the Android app's job
is to collect payment and report identifiers back. This backend's job
is to independently verify those identifiers before ever touching a
Subscription row. verify_payment_signature() below is the actual proof
a payment happened — a client-reported "Razorpay said success" is not
trusted on its own, and the webhook endpoint exists as a second,
independent confirmation path for exactly the case where the app's own
verify-payment call never lands (crash, connection drop, etc. right
after Razorpay's local success callback).
"""
import json
import logging
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_shop_no_subscription
from app.models.plan import Plan
from app.models.order import Order
from app.models.subscription import Subscription
from app.models.processed_webhook_event import ProcessedWebhookEvent
from app.util.time_utils import utc_now
from app.schemas.subscription_payment_schema import (
    PlanOut, ValidateCouponRequest, ValidateCouponResponse,
    CreateOrderRequest, CreateOrderResponse,
    VerifyPaymentRequest, SubscriptionActionResponse,
)
from app.services import razorpay_service
from app.services.subscription_pricing_service import (
    get_active_plan, validate_coupon_for_shop, compute_pricing_breakdown,
)
from app.services.subscription_activation_service import activate_order
from app.services.subscription_entitlement_service import (
    is_trial_offerable, classify_transition, apply_transition,
    compute_upgrade_credit_paise,
)
from app.services.rate_limit_service import check_rate_limit
from app.services.app_config_service import get_config_int
from app.services.audit_log_service import log_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/subscription", tags=["Subscription Payments"])


def _reject_if_downgrade(transition: str, current_sub) -> None:
    """
    Downgrading (Premium -> Base) is blocked entirely while the current
    Premium period is still running — deliberately simple, matching the
    "block it" option chosen over building a scheduled/deferred-downgrade
    feature. Without this, a shop could buy Base mid-cycle and the write
    path (apply_transition) would immediately overwrite the subscription
    to Base, discarding whatever paid Premium time was left, while still
    being charged full Base price with no credit — never charge for a
    purchase that would destroy value the shop already paid for.
    """
    if transition != "downgrade":
        return
    expiry_str = current_sub.expiry_date.isoformat() if current_sub and current_sub.expiry_date else "your current period ends"
    raise HTTPException(
        status_code=400,
        detail=(
            "You're on an active Premium subscription. Switching to Base isn't "
            f"available until your current Premium period ends ({expiry_str}) — "
            "come back after that to switch, or keep Premium and renew instead."
        ),
    )


@router.get("/plans", response_model=list[PlanOut])
def list_plans(
    db: Session = Depends(get_db),
    current_shop=Depends(get_current_shop_no_subscription),
):
    """
    Plan list — requires login (a valid shop session), but deliberately
    no subscription/tier requirement, since a shop with no subscription
    at all must still be able to see what it can buy. The app must
    always render prices from this response, never hardcode them.
    """
    return db.query(Plan).filter(Plan.is_active == True).all()


@router.post("/validate-coupon", response_model=ValidateCouponResponse)
def validate_coupon(
    body: ValidateCouponRequest,
    db: Session = Depends(get_db),
    current_shop=Depends(get_current_shop_no_subscription),
):
    check_rate_limit("validate-coupon", str(current_shop.id), max_hits=10, window_seconds=60)

    plan = get_active_plan(db, body.plan_code)
    coupon = validate_coupon_for_shop(db, body.coupon_code, current_shop.id)

    # Preview the same upgrade credit create-order will actually apply,
    # so the coupon screen's total matches what create-order returns a
    # moment later — never a separate/approximate calculation. Computed
    # BEFORE compute_pricing_breakdown (bug fix — see that function's
    # doc comment) so service charge/GST are taxed on the correct
    # post-credit payable amount, not the full plan price.
    current_sub = (
        db.query(Subscription)
        .filter(Subscription.shop_id == current_shop.id)
        .order_by(Subscription.expiry_date.desc())
        .first()
    )
    upgrade_credit = 0
    transition = classify_transition(current_sub, plan, is_trial=False)
    _reject_if_downgrade(transition, current_sub)
    if transition == "upgrade":
        upgrade_credit = compute_upgrade_credit_paise(db, current_sub, plan)

    breakdown = compute_pricing_breakdown(plan, coupon, credit_paise=upgrade_credit)
    final_amount = breakdown["final_amount_paise"]

    return ValidateCouponResponse(
        valid=True,
        original_amount_paise=breakdown["original_amount_paise"],
        discount_amount_paise=breakdown["discount_amount_paise"],
        subtotal_after_discount_paise=breakdown["subtotal_after_discount_paise"],
        service_charge_paise=breakdown["service_charge_paise"],
        gst_paise=breakdown["gst_paise"],
        final_amount_paise=final_amount,
        upgrade_credit_paise=upgrade_credit,
    )


@router.post("/create-order", response_model=CreateOrderResponse)
def create_order(
    body: CreateOrderRequest,
    db: Session = Depends(get_db),
    current_shop=Depends(get_current_shop_no_subscription),
):
    check_rate_limit("create-order", str(current_shop.id), max_hits=10, window_seconds=60)

    plan = get_active_plan(db, body.plan_code)

    coupon = None
    if body.coupon_code:
        coupon = validate_coupon_for_shop(db, body.coupon_code, current_shop.id)

    # Entitlement classification — decides whether this purchase is a
    # fresh buy, a renewal, an upgrade, or a downgrade based on the
    # shop's CURRENT subscription, and (for an upgrade) credits unused
    # Base time toward the amount actually charged. See
    # subscription_entitlement_service.compute_upgrade_credit_paise —
    # the credit is based on what the shop actually paid last time
    # (Order.amount_paise), never the plan's list price, so a
    # coupon-discounted original purchase can't over-credit here.
    current_sub = (
        db.query(Subscription)
        .filter(Subscription.shop_id == current_shop.id)
        .order_by(Subscription.expiry_date.desc())
        .first()
    )
    transition = classify_transition(current_sub, plan, is_trial=False)
    _reject_if_downgrade(transition, current_sub)

    credit_applied = 0
    if transition == "upgrade":
        credit_applied = compute_upgrade_credit_paise(db, current_sub, plan)

    # Server-computed final price — the app never sends an amount.
    # credit_applied is passed in BEFORE service charge/GST are computed
    # (bug fix — see compute_pricing_breakdown's doc comment: this used
    # to tax the full plan price and only subtract the credit from the
    # final total afterward, roughly doubling the correct amount on an
    # upgrade). final_amount is what actually gets charged.
    breakdown = compute_pricing_breakdown(plan, coupon, credit_paise=credit_applied)
    final_amount = breakdown["final_amount_paise"]

    # Sanity bounds (plan §6/§7) — cheap insurance against a bug or
    # tampering upstream (e.g. a malformed Plan row, or a future coupon
    # type with a rounding error) producing a nonsensical order before it
    # ever reaches Razorpay. Not a substitute for compute_pricing_breakdown's
    # own floor-at-zero logic — a second, independent check.
    if final_amount < 0 or final_amount > 10_000_000:  # ₹0 .. ₹1,00,000
        logger.error("Rejected out-of-bounds order amount %s for shop %s plan %s", final_amount, current_shop.id, body.plan_code)
        raise HTTPException(status_code=400, detail="Invalid order amount")

    # Idempotency: reuse an existing, still-pending order for the exact
    # same shop+plan+coupon combo rather than spawning a duplicate
    # Razorpay order on a double-tap or a retried request. "Pending" here
    # means created in the last few minutes and not yet resolved either
    # way.
    recent_cutoff = utc_now() - timedelta(minutes=10)
    existing = (
        db.query(Order)
        .filter(
            Order.shop_id == current_shop.id,
            Order.plan_code == body.plan_code,
            Order.coupon_code == body.coupon_code,
            Order.status == "created",
            Order.created_at >= recent_cutoff,
        )
        .order_by(Order.created_at.desc())
        .first()
    )
    # BUG FIXED HERE: this used to assume Order.amount_paise always still
    # matched `breakdown` (recomputed fresh, just above) since "plan
    # price + coupon + service charge + GST don't change between the
    # original request and this retry" — true before upgrade credit
    # existed, but credit_applied is now time-sensitive (it shrinks as
    # remaining_days ticks down every second). Confirm-and-pay prefetches
    # an order the moment the screen opens, then reuses it when Pay is
    # tapped moments/minutes later — during that gap the reused order's
    # actual amount_paise (what Razorpay was already told and will
    # charge) could drift below a freshly recomputed breakdown (less
    # elapsed time = more credit = lower total), while the OLD response
    # still echoed back the NEW breakdown's subtotal/service/GST fields.
    # That mismatch (app total ₹361.48 vs Razorpay's actual ₹361.08) is
    # exactly what was reported. Only reuse the existing order when its
    # stored amount still equals what breakdown says RIGHT NOW — anything
    # else falls through and creates a brand-new, fully consistent order
    # instead of returning stale-vs-fresh numbers together.
    if existing and existing.razorpay_order_id and existing.amount_paise == final_amount:
        return CreateOrderResponse(
            order_db_id=existing.id,
            razorpay_order_id=existing.razorpay_order_id,
            razorpay_key_id=razorpay_service.get_public_key_id(),
            amount_paise=existing.amount_paise,
            subtotal_after_discount_paise=breakdown["subtotal_after_discount_paise"],
            service_charge_paise=breakdown["service_charge_paise"],
            gst_paise=breakdown["gst_paise"],
            upgrade_credit_paise=credit_applied,
            is_free=False,
        )

    # Zero-amount branch (e.g. a 100%-off coupon) — Razorpay's checkout
    # does not support a ₹0 charge, so skip it entirely and activate
    # directly. See plan §6.1. A 100%-off coupon zeroes the subtotal,
    # which zeroes the service charge and GST too since both are
    # percentages of that subtotal — so this branch still only triggers
    # on a genuinely free order, not a "cheap after discount" one.
    if final_amount == 0:
        order = Order(
            shop_id=current_shop.id,
            plan_code=body.plan_code,
            coupon_code=body.coupon_code,
            amount_paise=0,
            status="created",
        )
        db.add(order)
        db.commit()
        db.refresh(order)

        activate_order(db, order, razorpay_payment_id=None)
        log_event(db, current_shop.id, "order_free_activated", f"plan={body.plan_code} coupon={body.coupon_code}", amount_paise=0)

        return CreateOrderResponse(
            order_db_id=order.id,
            razorpay_order_id="",
            razorpay_key_id="",
            amount_paise=0,
            subtotal_after_discount_paise=0,
            service_charge_paise=0,
            gst_paise=0,
            upgrade_credit_paise=credit_applied,
            is_free=True,
        )

    # Normal paid path — create the Order row first (so there's always a
    # server-side record even if the Razorpay API call itself fails),
    # then create the actual Razorpay order.
    order = Order(
        shop_id=current_shop.id,
        plan_code=body.plan_code,
        coupon_code=body.coupon_code,
        amount_paise=final_amount,
        status="created",
        order_type=transition,
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    try:
        rp_order = razorpay_service.create_razorpay_order(
            amount_paise=final_amount,
            receipt=f"order_{order.id}",
            notes={"shop_id": str(current_shop.id), "plan_code": body.plan_code},
        )
    except Exception:
        order.status = "failed"
        db.commit()
        logger.exception("Razorpay order creation failed for order %s", order.id)
        log_event(db, current_shop.id, "order_creation_failed", f"order_id={order.id} plan={body.plan_code}", amount_paise=final_amount)
        raise HTTPException(status_code=502, detail="Could not start payment. Please try again.")

    order.razorpay_order_id = rp_order["id"]
    db.commit()

    log_event(db, current_shop.id, "order_created", f"plan={body.plan_code} coupon={body.coupon_code} razorpay_order_id={rp_order['id']}", amount_paise=final_amount)

    return CreateOrderResponse(
        order_db_id=order.id,
        razorpay_order_id=rp_order["id"],
        razorpay_key_id=razorpay_service.get_public_key_id(),
        amount_paise=final_amount,
        subtotal_after_discount_paise=breakdown["subtotal_after_discount_paise"],
        service_charge_paise=breakdown["service_charge_paise"],
        gst_paise=breakdown["gst_paise"],
        upgrade_credit_paise=credit_applied,
        is_free=False,
    )


@router.post("/verify-payment", response_model=SubscriptionActionResponse)
def verify_payment(
    body: VerifyPaymentRequest,
    db: Session = Depends(get_db),
    current_shop=Depends(get_current_shop_no_subscription),
):
    order = db.query(Order).filter(Order.id == body.order_db_id).first()
    if not order or order.shop_id != current_shop.id:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.razorpay_order_id != body.razorpay_order_id:
        raise HTTPException(status_code=400, detail="Order mismatch")

    # The actual proof of payment — see module docstring.
    if not razorpay_service.verify_payment_signature(
        body.razorpay_order_id, body.razorpay_payment_id, body.razorpay_signature
    ):
        log_event(db, current_shop.id, "payment_verification_failed", f"order_id={order.id} razorpay_payment_id={body.razorpay_payment_id}", amount_paise=order.amount_paise)
        raise HTTPException(status_code=400, detail="Payment verification failed")

    sub = activate_order(db, order, razorpay_payment_id=body.razorpay_payment_id)
    log_event(db, current_shop.id, "payment_verified", f"order_id={order.id} razorpay_payment_id={body.razorpay_payment_id}", amount_paise=order.amount_paise)

    return SubscriptionActionResponse(
        success=True,
        status=sub.status,
        tier=sub.tier,
        plan=sub.plan,
        expiry_date=sub.expiry_date.isoformat() if sub.expiry_date else None,
    )


@router.post("/razorpay-webhook")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Independent confirmation path — required, not optional, per plan
    §3.1/§3.3. Catches the case where the app's own verify-payment call
    never lands (app crash, connection drop right after Razorpay's local
    success callback) but the payment genuinely went through.

    No shop-scoped auth here (Razorpay is the caller, not the app) —
    trust instead comes entirely from the webhook signature check below,
    which is why that check must never be skipped or made optional.
    """
    raw_body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    if not razorpay_service.verify_webhook_signature(raw_body, signature):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    payload = json.loads(raw_body)
    event_id = payload.get("event_id") or request.headers.get("X-Razorpay-Event-Id")
    event_type = payload.get("event")

    # Dedup — Razorpay can and does resend the same event on retries.
    if event_id:
        already_processed = (
            db.query(ProcessedWebhookEvent)
            .filter(ProcessedWebhookEvent.razorpay_event_id == event_id)
            .first()
        )
        if already_processed:
            return {"status": "already_processed"}

    if event_type == "payment.captured":
        payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
        rp_order_id = payment_entity.get("order_id")
        rp_payment_id = payment_entity.get("id")

        order = db.query(Order).filter(Order.razorpay_order_id == rp_order_id).first()
        if order:
            activate_order(db, order, razorpay_payment_id=rp_payment_id)
            log_event(db, order.shop_id, "payment_verified_via_webhook", f"order_id={order.id} razorpay_payment_id={rp_payment_id}", amount_paise=order.amount_paise)
        else:
            logger.warning("Webhook payment.captured for unknown razorpay_order_id=%s", rp_order_id)

    if event_id:
        db.add(ProcessedWebhookEvent(razorpay_event_id=event_id, event_type=event_type))
        db.commit()

    return {"status": "ok"}


@router.post("/start-trial", response_model=SubscriptionActionResponse)
def start_trial(
    db: Session = Depends(get_db),
    current_shop=Depends(get_current_shop_no_subscription),
):
    """
    Explicit, user-initiated free trial — never started automatically at
    registration (plan §4.2: burning trial days before the user has even
    opened the app is wasted runway). Grants full Premium access for
    trial_duration_days (backend-controlled via app_config, never
    hardcoded in the app — plan §4.1).

    One trial per shop, enforced here via Shop.has_used_trial, which is
    set server-side and not resettable by re-logging in or clearing
    local app state (plan §4.3).
    """
    check_rate_limit("start-trial", str(current_shop.id), max_hits=5, window_seconds=60)

    if current_shop.has_used_trial:
        raise HTTPException(status_code=400, detail="You've already used your free trial")

    sub = db.query(Subscription).filter(Subscription.shop_id == current_shop.id).first()

    # Entitlement gate — this is the fix for "starting a trial silently
    # clobbers an active paid Base subscription". has_used_trial alone
    # (checked above) is not enough; a live active_base/active_premium
    # subscription must also block a trial, even for a shop that's never
    # technically "used" one.
    if not is_trial_offerable(current_shop.has_used_trial, sub):
        raise HTTPException(
            status_code=400,
            detail="A trial isn't available while you have an active subscription",
        )

    trial_days = get_config_int(db, "trial_duration_days")
    trial_plan = Plan(plan_code="trial", tier="premium", duration_days=trial_days, price_paise=0, name="Trial")
    sub = apply_transition(db, sub, current_shop.id, trial_plan, "trial_start")

    current_shop.has_used_trial = True
    # Onboarding step 1 complete — see the matching comment in
    # subscription_activation_service.activate_order() for the same
    # set-once-never-unset reasoning.
    if not current_shop.onboarding_subscription_done:
        current_shop.onboarding_subscription_done = True
    db.commit()
    db.refresh(sub)

    log_event(db, current_shop.id, "trial_started", f"trial_days={trial_days}")

    return SubscriptionActionResponse(
        success=True,
        status=sub.status,
        tier=sub.tier,
        plan=sub.plan,
        expiry_date=sub.expiry_date.isoformat() if sub.expiry_date else None,
    )
