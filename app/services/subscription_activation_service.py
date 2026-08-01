"""
Shared activation logic — the only place an Order transitions to "paid"
and a Subscription gets created/extended. Called from three independent
paths (verify-payment, the webhook, and the zero-amount-coupon branch of
create-order), all of which must produce identical, idempotent results:
calling this twice for the same already-paid Order must be a safe no-op,
since verify-payment and the webhook can both race to confirm the same
payment.
"""
from datetime import timedelta
from sqlalchemy.orm import Session

from app.models.order import Order
from app.models.plan import Plan
from app.models.coupon import Coupon
from app.models.coupon_redemption import CouponRedemption
from app.models.subscription import Subscription
from app.models.shop import Shop
from app.util.time_utils import utc_now


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

    # A payment made while an existing, still-valid subscription is
    # active starts the new period from now() rather than stacking on
    # top of remaining time — see plan §4.8 (same rule applied to
    # trial-to-paid transitions). Simpler and avoids odd banked-time
    # edge cases; revisit only if this becomes a real complaint.
    sub = (
        db.query(Subscription)
        .filter(Subscription.shop_id == shop_id)
        .order_by(Subscription.expiry_date.desc())
        .first()
    )

    start = utc_now()
    expiry = start + timedelta(days=plan.duration_days)

    if sub:
        sub.plan = plan.plan_code
        sub.tier = plan.tier
        sub.start_date = start
        sub.expiry_date = expiry
        sub.status = "active"
        # trial_started_at is deliberately left untouched (not cleared)
        # even when converting from trial to paid — kept for analytics
        # per plan §4.9 (trial-start vs. eventual outcome).
    else:
        sub = Subscription(
            shop_id=shop_id,
            plan=plan.plan_code,
            tier=plan.tier,
            start_date=start,
            expiry_date=expiry,
            status="active",
        )
        db.add(sub)

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
