"""
Single source of truth for "what does this shop's current subscription
state mean, and what should happen to it when a new trial/paid
transition is requested."

Root cause this file fixes: /start-trial and activate_order() used to
each independently overwrite the shop's one Subscription row with zero
awareness of what was there before. That blind-overwrite pattern caused
two real, reported bugs:

  1. A shop on an active, paid Base plan could tap "Start free trial"
     and the trial would silently clobber the paid subscription,
     discarding the remaining paid days with no warning.
  2. A shop on Base buying Premium was treated identically to a shop
     buying for the first time — no credit for Base days already paid
     for, and no record of what actually happened (upgrade vs. fresh
     purchase) for later reporting/support.

Every route that creates or extends a Subscription (start-trial,
create-order, activate_order) must go through classify_transition() +
apply_transition() here instead of writing the row directly.
"""
from datetime import timedelta
from typing import Literal, Optional
from sqlalchemy.orm import Session

from app.models.subscription import Subscription
from app.models.order import Order
from app.models.plan import Plan
from app.util.time_utils import utc_now


EntitlementState = Literal["no_plan", "trialing", "active_base", "active_premium", "expired"]

TransitionType = Literal["fresh", "trial_start", "trial_convert", "renewal", "upgrade", "downgrade"]


def resolve_entitlement_state(sub: Optional[Subscription]) -> EntitlementState:
    """
    Classifies the shop's CURRENT subscription row into one of five
    states. This is the one place that decision is made — every other
    function in this module, and every route, must call this rather than
    re-deriving "is this shop premium/expired/etc" from raw field checks.
    """
    if sub is None:
        return "no_plan"
    # Two independent ways a subscription can be "over", and both must
    # resolve to "expired" here: (1) time-based — expiry_date has
    # passed, regardless of whether the daily expiry sweep has gotten
    # around to flipping sub.status yet; (2) an explicit status
    # override — e.g. an admin refund sets status="expired" immediately
    # without touching expiry_date, since "this is no longer valid right
    # now" is not the same claim as "this was never going to expire
    # until a later date." Checking expiry_date alone misses case (2).
    if sub.status == "expired":
        return "expired"
    if sub.expiry_date and sub.expiry_date <= utc_now():
        return "expired"
    if sub.status == "trial":
        return "trialing"
    if sub.tier == "premium":
        return "active_premium"
    if sub.tier == "base":
        return "active_base"
    # Defensive fallback for any legacy row with an unrecognized
    # tier/status combination — treat as no_plan (i.e. "trial/purchase
    # allowed") rather than silently blocking every future transition.
    return "no_plan"


def is_trial_offerable(shop_has_used_trial: bool, sub: Optional[Subscription]) -> bool:
    """
    Whether the trial card/start-trial button should be reachable at
    all. Deliberately NOT just `not shop_has_used_trial` (the old rule,
    which is why the trial card kept showing for a shop already on a
    paid Base plan) — a live active_base or active_premium subscription
    always blocks it too, regardless of trial history.
    """
    if shop_has_used_trial:
        return False
    return resolve_entitlement_state(sub) in ("no_plan", "expired")


def classify_transition(sub: Optional[Subscription], new_plan: Plan, is_trial: bool) -> TransitionType:
    """
    Decides what KIND of transition a requested trial-start or
    plan-purchase actually is, given the shop's current state. Raises
    ValueError for a transition that should never be reachable (the
    caller is expected to have already checked is_trial_offerable() /
    surfaced a clean 400 before getting here — this is a second,
    defensive check, not the primary UX gate).
    """
    state = resolve_entitlement_state(sub)

    if is_trial:
        if state in ("no_plan", "expired"):
            return "trial_start"
        raise ValueError(f"Trial is not offerable from entitlement state {state!r}")

    if state in ("no_plan", "expired"):
        return "fresh"
    if state == "trialing":
        return "trial_convert"
    if state == "active_base":
        return "renewal" if new_plan.tier == "base" else "upgrade"
    if state == "active_premium":
        return "downgrade" if new_plan.tier == "base" else "renewal"

    raise ValueError(f"Unhandled entitlement state {state!r}")  # pragma: no cover


def compute_upgrade_credit_paise(db: Session, sub: Optional[Subscription], new_plan: Plan) -> int:
    """
    Paise to subtract from an upgrade purchase's price for the shop's
    unused time on their current plan. Based on what the shop ACTUALLY
    PAID for their current period (Subscription.funding_order_id ->
    Order.amount_paise) — never Plan.price_paise — so a coupon-
    discounted original purchase can never produce an inflated credit.

    Always returns a value in [0, new_plan.price_paise]; never raises.
    Falls back to 0 for every case where a real credit can't be safely
    computed (no subscription, no remaining time, no funding order on
    record, funding order not actually paid, or the referenced plan
    having somehow been deleted) — an unknown/uncomputable credit must
    never block a purchase or go negative, it just means "no discount".
    """
    if sub is None or sub.expiry_date is None:
        return 0

    remaining_seconds = (sub.expiry_date - utc_now()).total_seconds()
    if remaining_seconds <= 0:
        return 0

    if not sub.funding_order_id:
        return 0

    order = (
        db.query(Order)
        .filter(Order.id == sub.funding_order_id, Order.status == "paid")
        .first()
    )
    if order is None or order.amount_paise <= 0:
        return 0

    old_plan = db.query(Plan).filter(Plan.plan_code == order.plan_code).first()
    if old_plan is None or not old_plan.duration_days:
        return 0

    remaining_days = remaining_seconds / 86400.0
    fraction = min(1.0, remaining_days / old_plan.duration_days)
    credit = round(fraction * order.amount_paise)

    # Never let the credit exceed the new plan's own price — an
    # unused-time credit must reduce a purchase toward zero, not make it
    # negative or "free plus cash back".
    return max(0, min(credit, new_plan.price_paise))


def apply_transition(
    db: Session,
    sub: Optional[Subscription],
    shop_id: int,
    new_plan: Plan,
    transition: TransitionType,
    funding_order_id: Optional[int] = None,
) -> Subscription:
    """
    Writes the Subscription row for an already-classified transition.
    Does NOT commit — callers commit as part of their own transaction
    (matching the existing activate_order/start_trial pattern, so
    coupon-redemption/shop-flag writes in the same request stay atomic
    with this).

    "renewal" extends from the CURRENT expiry_date (never from now) so
    paid-for time already on the books is never lost. Every other
    transition (fresh/trial_start/trial_convert/upgrade/downgrade)
    starts a fresh full-duration period from now — deliberately simple;
    an upgrade does not try to splice "remaining premium days" onto a
    new premium period, it converts the remaining Base value into a
    price credit instead (see compute_upgrade_credit_paise), which
    avoids ever having to reason about mismatched period boundaries.
    """
    is_trial = transition == "trial_start"
    start = utc_now()

    if transition == "renewal" and sub is not None and sub.expiry_date and sub.expiry_date > start:
        period_start = sub.expiry_date
    else:
        period_start = start

    expiry = period_start + timedelta(days=new_plan.duration_days)

    if sub is None:
        sub = Subscription(shop_id=shop_id)
        db.add(sub)

    sub.plan = new_plan.plan_code
    sub.tier = new_plan.tier
    sub.start_date = start
    sub.expiry_date = expiry
    sub.status = "trial" if is_trial else "active"

    if is_trial:
        sub.trial_started_at = start
    # trial_started_at is deliberately left untouched on every other
    # transition (including trial_convert) — kept for analytics even
    # after the shop moves to paid, per the original activate_order
    # comment this replaces.

    if funding_order_id is not None:
        sub.funding_order_id = funding_order_id

    return sub
