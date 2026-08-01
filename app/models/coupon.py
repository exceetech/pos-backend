from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime
from app.database import Base


class Coupon(Base):
    """
    Discount coupons for subscription purchases. Validation (expiry,
    active flag, global and per-shop usage caps) must always happen
    server-side in POST /subscription/validate-coupon and again inside
    POST /subscription/create-order — never trust a client-sent discount
    amount.
    """
    __tablename__ = "coupons"

    id = Column(Integer, primary_key=True, index=True)

    code = Column(String, unique=True, index=True, nullable=False)

    # percentage | flat
    discount_type = Column(String, nullable=False)
    discount_value = Column(Float, nullable=False)

    valid_from = Column(DateTime, nullable=True)
    valid_until = Column(DateTime, nullable=True)

    # NULL = unlimited global uses.
    max_uses = Column(Integer, nullable=True)
    times_used = Column(Integer, default=0, nullable=False)

    # Per-shop cap, independent of the global cap above — defaults to
    # single-use-per-shop, the safer default for a coupon meant to
    # incentivize one signup rather than being repeatedly reapplied by
    # the same shop.
    max_uses_per_shop = Column(Integer, default=1, nullable=False)

    is_active = Column(Boolean, default=True, nullable=False)
