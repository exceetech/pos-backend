"""
Shared activation logic — the only place an Order transitions to "paid"
and a Subscription gets created/extended. Called from three independent
paths (verify-payment, the webhook, and the zero-amount-coupon branch of
create-order), all of which must produce identical, idempotent results:
calling this twice for the same already-paid Order must be a safe no-op,
since verify-payment and the webhook can both race to confirm the same
payment.
"""
from sqlalchemy.orm import Session

from app.models.order import Order
from app.models.plan import Plan
from app.models.coupon import Coupon
from app.models.coupon_redemption import CouponRedemption
from app.models.subscription import Subscription
from app.models.shop import Shop
from app.util.time_utils import utc_now
from app.services.subscription_entitlement_service import (
    classify_transition, apply_transition,
)


def activate_order(db: Session, order: Order, razorpay_payment_id: str | None) -> Subscription:
    """
    Marks `order` paid and creates/extends the shop's Subscription
    accordingly, all in one transaction. Safe to call more than once for
    the same order — if it's already "paid", returns the existing
    subscription untouched instead of double-extending it or
    double-counting the coupon.
    """
    shop_id = order.shop_id

    # Idempotency guard — this is what makes it safe for verify-payment
    # and the webhook to both land for the same payment.
    if order.status == "paid":
        return (
            db.query(Subscription)
            .filter(Subscription.shop_id == shop_id)
            .order_by(Subscription.expiry_date.desc())
            .first()
        )

    plan = db.query(Plan).filter(Plan.plan_code == order.plan_code).first()
    if plan is None:
        raise ValueError(f"Order {order.id} references unknown plan_code {order.plan_code!r}")

    order.status = "paid"
    order.verified_at = utc_now()
    if razorpay_payment_id:
        order.razorpay_payment_id = razorpay_payment_id

    # Entitlement-aware transition — replaces the old blind overwrite.
    # classify_transition() looks at whatever subscription state the shop
    # is ACTUALLY in right now (no_plan/expired/trialing/active_base/
    # active_premium) and decides whether this payment is a fresh
    # purchase, a renewal (extends from current expiry, not now), an
    # upgrade, a downgrade, or a trial→paid conversion. See
    # subscription_entitlement_service for the full reasoning — this is
    # what fixes the "Base subscription silently discarded" and
    # "no upgrade credit" bugs.
    sub = (
        db.query(Subscription)
        .filter(Subscription.shop_id == shop_id)
        .order_by(Subscription.expiry_date.desc())
        .first()
    )

    transition = classify_transition(sub, plan, is_trial=False)
    if transition == "downgrade":
        # Defense in depth — create_order already rejects a downgrade
        # purchase before any Order is created (see
        # subscription_payment_routes._reject_if_downgrade), so a paid
        # Order should never reach here classified as a downgrade. If it
        # somehow does (e.g. entitlement state changed between
        # create-order and payment confirmation), fail loudly instead of
        # silently discarding the shop's remaining Premium period.
        raise ValueError(
            f"Order {order.id} resolved to a downgrade transition, which should "
            "have been rejected at create-order time — refusing to activate."
        )
    sub = apply_transition(
        db, sub, shop_id, plan, transition, funding_order_id=order.id,
    )
    order.order_type = transition

    # Coupon redemption — atomic in the same transaction as the paid
    # status flip, so two near-simultaneous payments can't both read
    # "under the cap" and both redeem past a coupon's max_uses_per_shop.
    if order.coupon_code:
        coupon = db.query(Coupon).filter(Coupon.code == order.coupon_code).first()
        if coupon:
            coupon.times_used = (coupon.times_used or 0) + 1
            db.add(CouponRedemption(coupon_id=coupon.id, shop_id=shop_id, order_id=order.id))

    # Onboarding step 1 (subscription) is complete the moment a shop
    # obtains ANY real subscription — paid or the free base_monthly plan.
    # Set-once, never unset: a later expiry must not undo a completed
    # onboarding step (plan §2.6), so this only ever flips False → True.
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if shop and not shop.onboarding_subscription_done:
        shop.onboarding_subscription_done = True

    db.commit()
    db.refresh(sub)
    return sub
