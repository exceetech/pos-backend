"""
Server-side price computation for subscription purchases. This is the
one rule that must never be bent: the app sends a plan_code and an
optional coupon_code, never an amount — this module is what turns those
into a final, trusted price. Used identically by
POST /subscription/validate-coupon (preview) and
POST /subscription/create-order (the real charge), so a coupon can never
show one discounted price and charge a different one.
"""
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.plan import Plan
from app.models.coupon import Coupon
from app.models.coupon_redemption import CouponRedemption
from app.util.time_utils import utc_now


def get_active_plan(db: Session, plan_code: str) -> Plan:
    plan = db.query(Plan).filter(Plan.plan_code == plan_code, Plan.is_active == True).first()
    if not plan:
        raise HTTPException(status_code=400, detail="Unknown or inactive plan")
    return plan


def validate_coupon_for_shop(db: Session, coupon_code: str, shop_id: int) -> Coupon:
    """
    Raises HTTPException(400, ...) with a clear reason on any failure —
    expired, not yet valid, inactive, globally exhausted, or already used
    by this shop up to its per-shop cap. Never trust a client-sent
    discount amount; this is the only place a coupon's validity is
    decided.
    """
    coupon = db.query(Coupon).filter(Coupon.code == coupon_code).first()
    if not coupon or not coupon.is_active:
        raise HTTPException(status_code=400, detail="Invalid coupon code")

    now = utc_now()
    if coupon.valid_from and now < coupon.valid_from:
        raise HTTPException(status_code=400, detail="Coupon is not active yet")
    if coupon.valid_until and now > coupon.valid_until:
        raise HTTPException(status_code=400, detail="Coupon has expired")

    if coupon.max_uses is not None and coupon.times_used >= coupon.max_uses:
        raise HTTPException(status_code=400, detail="Coupon usage limit reached")

    shop_uses = (
        db.query(CouponRedemption)
        .filter(CouponRedemption.coupon_id == coupon.id, CouponRedemption.shop_id == shop_id)
        .count()
    )
    if shop_uses >= coupon.max_uses_per_shop:
        raise HTTPException(status_code=400, detail="You've already used this coupon")

    return coupon


# Platform service charge and GST, applied on top of the (possibly
# coupon-discounted) plan price. Both are fixed platform-wide rates, not
# per-plan or per-coupon — change here if either ever needs to vary.
SERVICE_CHARGE_PERCENT = 2.0
GST_PERCENT = 18.0


def _discounted_subtotal(plan: Plan, coupon: Coupon | None) -> tuple[int, int]:
    """Returns (discount_amount_paise, subtotal_after_discount_paise).
    Discount floored so the subtotal never goes negative."""
    price = plan.price_paise
    if coupon is None:
        return 0, price

    if coupon.discount_type == "percentage":
        discount = round(price * (coupon.discount_value / 100.0))
    elif coupon.discount_type == "flat":
        discount = round(coupon.discount_value)
    else:
        discount = 0

    discount = min(discount, price)
    return discount, price - discount


def compute_final_price(plan: Plan, coupon: Coupon | None) -> int:
    """Returns amount_paise after discount only (no service charge/GST) —
    kept for callers that just need the discounted plan price itself."""
    _, subtotal = _discounted_subtotal(plan, coupon)
    return subtotal


def compute_pricing_breakdown(plan: Plan, coupon: Coupon | None, credit_paise: int = 0) -> dict:
    """
    Full charged-amount breakdown: plan price -> coupon discount ->
    upgrade credit -> 2% service charge -> 18% GST (service charge is
    added to the taxable base before GST, matching how the service
    charge is itself a taxable service fee) -> final amount. This is
    what actually gets charged via Razorpay and stored on the Order
    row — the app's price summary must always mirror these exact
    fields, never compute its own copy of this math, so the displayed
    total can never drift from what's charged.

    BUG FIXED HERE: credit_paise (the shop's unused-time credit on a
    Base->Premium upgrade, see
    subscription_entitlement_service.compute_upgrade_credit_paise) used
    to be subtracted from final_amount AFTER service charge and GST had
    already been computed on the full, uncredited plan price — e.g. for
    a ₹999 Premium plan with a ₹699 Base credit, service charge and GST
    were being charged on the full ₹999 (giving ~₹1,202 pre-credit) and
    only THEN was ₹699 subtracted, instead of taxing the correct ₹300
    payable amount (₹999 - ₹699) to begin with. That produced a final
    total roughly double what it should have been. credit_paise is now
    subtracted from the subtotal BEFORE service charge/GST are computed,
    so both are correctly calculated on the actual payable amount.
    """
    discount, subtotal = _discounted_subtotal(plan, coupon)
    payable = max(0, subtotal - max(0, credit_paise))

    service_charge = round(payable * (SERVICE_CHARGE_PERCENT / 100.0))
    taxable = payable + service_charge
    gst = round(taxable * (GST_PERCENT / 100.0))
    final = taxable + gst

    return {
        "original_amount_paise": plan.price_paise,
        "discount_amount_paise": discount,
        "subtotal_after_discount_paise": payable,
        "service_charge_paise": service_charge,
        "gst_paise": gst,
        "final_amount_paise": final,
    }
