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
    final_amount_paise: int


class CreateOrderRequest(BaseModel):
    plan_code: str
    coupon_code: Optional[str] = None


class CreateOrderResponse(BaseModel):
    order_db_id: int
    razorpay_order_id: str
    razorpay_key_id: str
    amount_paise: int
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
