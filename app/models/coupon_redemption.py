from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from app.database import Base
from app.util.time_utils import utc_now


class CouponRedemption(Base):
    """
    One row per shop-coupon usage. Needed because Coupon.times_used alone
    (a single global counter) can't answer "how many times has THIS shop
    used THIS coupon" — that's what max_uses_per_shop enforcement checks
    against. Written in the same DB transaction that marks an Order paid,
    so a coupon's per-shop cap can't be raced past by two near-simultaneous
    payment attempts.
    """
    __tablename__ = "coupon_redemptions"

    id = Column(Integer, primary_key=True, index=True)

    coupon_id = Column(Integer, ForeignKey("coupons.id"), nullable=False)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)

    redeemed_at = Column(DateTime, default=utc_now)  # Bucket B, see order.py
