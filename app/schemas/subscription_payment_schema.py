from pydantic import BaseModel
from typing import Optional


class PlanOut(BaseModel):
    plan_code: str
    name: str
    tier: str
    price_paise: int
    duration_days: int

    class Config:
        from_attributes = True


class ValidateCouponRequest(BaseModel):
    plan_code: str
    coupon_code: str


class ValidateCouponResponse(BaseModel):
    valid: bool
    original_amount_paise: int
    discount_amount_paise: int
    # Plan price minus coupon discount, before service charge/GST —
    # kept for backward compatibility with any caller that only wants
    # the discounted plan price itself.
    subtotal_after_discount_paise: int
    service_charge_paise: int
    gst_paise: int
    # The true charged amount: subtotal + service charge + GST. The app
    # must display this as "Total", not original/discount alone.
    final_amount_paise: int
    # Non-zero only when this purchase is an upgrade from an existing
    # paid Base subscription — credit for unused Base time, already
    # subtracted from final_amount_paise. Based on what the shop actually
    # paid last time, not plan list price — see
    # subscription_entitlement_service.compute_upgrade_credit_paise.
    upgrade_credit_paise: int = 0


class CreateOrderRequest(BaseModel):
    plan_code: str
    coupon_code: Optional[str] = None


class CreateOrderResponse(BaseModel):
    order_db_id: int
    razorpay_order_id: str
    razorpay_key_id: str
    amount_paise: int
    subtotal_after_discount_paise: int
    service_charge_paise: int
    gst_paise: int
    upgrade_credit_paise: int = 0
    currency: str = "INR"
    # True when the discounted price is zero — the app must skip
    # Razorpay's checkout entirely and call verify-free-order instead
    # (see subscription_payment_routes.py). Razorpay's SDK does not
    # support a ₹0 charge.
    is_free: bool


class VerifyPaymentRequest(BaseModel):
    order_db_id: int
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class SubscriptionActionResponse(BaseModel):
    success: bool
    status: str
    tier: Optional[str] = None
    plan: Optional[str] = None
    expiry_date: Optional[str] = None


# ── Admin-only — coupon management, no Android client mirror needed ────────

class AdminCreateCouponRequest(BaseModel):
    code: str
    discount_type: str  # percentage | flat
    discount_value: float
    valid_from: Optional[str] = None   # ISO datetime/date string
    valid_until: Optional[str] = None  # ISO datetime/date string
    max_uses: Optional[int] = None
    max_uses_per_shop: int = 1


class AdminCouponOut(BaseModel):
    id: int
    code: str
    discount_type: str
    discount_value: float
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    max_uses: Optional[int] = None
    times_used: int
    max_uses_per_shop: int
    is_active: bool
