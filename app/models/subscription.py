from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from app.database import Base


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)

    shop_id = Column(Integer, ForeignKey("shops.id"))

    plan = Column(String)  # plan_code, e.g. base_monthly / premium_monthly

    start_date = Column(DateTime)
    expiry_date = Column(DateTime)

    # Valid values: trial | active | expired | inactive
    status = Column(String, default="active")

    # base | premium — read directly by tier-gate checks instead of the
    # historical pattern of string-matching `plan`. Every place that gates
    # GST/profit/AI-insights access must read THIS field, not `plan`.
    tier = Column(String, nullable=True)

    # Set only when status == "trial"; kept even after conversion to paid
    # for analytics (trial-start vs. eventual outcome).
    trial_started_at = Column(DateTime, nullable=True)