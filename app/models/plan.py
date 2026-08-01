from sqlalchemy import Column, Integer, String, Boolean, Float
from app.database import Base


class Plan(Base):
    """
    Central price list for subscription plans. The app must always fetch
    prices from GET /subscription/plans and never hardcode them — this
    table is the single source of truth so a price change is a backend
    edit, not an app release.
    """
    __tablename__ = "plans"

    id = Column(Integer, primary_key=True, index=True)

    plan_code = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)

    # base | premium — read by tier-gate checks via the Subscription this
    # plan produces (Subscription.tier is copied from here at
    # activation time, not looked up live on every gate check).
    tier = Column(String, nullable=False)

    price_paise = Column(Integer, nullable=False)  # smallest currency unit
    duration_days = Column(Integer, nullable=False)

    is_active = Column(Boolean, default=True, nullable=False)

    # Reserved for future finer-grained gating beyond a flat two-tier
    # split (e.g. "premium_lite"). Not required for the base/premium
    # launch — tier alone drives gating for now.
    feature_flags = Column(String, nullable=True)
