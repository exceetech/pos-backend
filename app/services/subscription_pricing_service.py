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


def compute_final_price(plan: Plan, coupon: Coupon | None) -> int:
    """Returns amount_paise after discount, floored at 0. Never negative."""
    price = plan.price_paise
    if coupon is None:
        return price

    if coupon.discount_type == "percentage":
        discount = round(price * (coupon.discount_value / 100.0))
    elif coupon.discount_type == "flat":
        discount = round(coupon.discount_value)
    else:
        discount = 0

    return max(price - discount, 0)
