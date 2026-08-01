from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from app.database import Base
from app.util.time_utils import utc_now


class Order(Base):
    """
    One row per checkout attempt, created BEFORE payment happens (at
    POST /subscription/create-order) so there's always a server-side
    record to reconcile against — whether the payment succeeds, fails,
    or the app loses connection mid-flow.

    status: created | paid | failed | refunded
    "created" rows stuck past a reasonable window are what the
    reconciliation job (Phase 9) checks against Razorpay's own order
    status API to catch payments that succeeded but never got confirmed
    back to this table (both verify-payment and the webhook failing to
    land is rare, but this table is what makes it recoverable rather
    than silently lost).
    """
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)

    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False)
    plan_code = Column(String, nullable=False)
    coupon_code = Column(String, nullable=True)

    # Server-computed final price after any discount — never a
    # client-sent amount. Zero after a 100%-off coupon is a valid value;
    # see the zero-amount branch in create-order (skips Razorpay entirely).
    amount_paise = Column(Integer, nullable=False)

    razorpay_order_id = Column(String, nullable=True, index=True)
    razorpay_payment_id = Column(String, nullable=True)

    status = Column(String, default="created", nullable=False)

    # Bucket B (technical bookkeeping timestamp, comparable to utc_now()
    # elsewhere in this codebase — e.g. Subscription.expiry_date) — NOT
    # local_now(), which is reserved for business event wall-clock times
    # like Bill.created_at. This matters concretely: the idempotency
    # window check in subscription_payment_routes.create_order() compares
    # this column against utc_now(), so a mismatched clock source here
    # would silently misfire that comparison by the server's UTC offset.
    created_at = Column(DateTime, default=utc_now)
    verified_at = Column(DateTime, nullable=True)
