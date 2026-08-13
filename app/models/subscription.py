from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from app.database import Base


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)

    # Every subscription lookup filters by shop_id (get_active_subscription
    # etc.), so this is a hot lookup path worth indexing.
    shop_id = Column(Integer, ForeignKey("shops.id"), index=True)

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

    # The Order that most recently paid for the CURRENT period — set by
    # subscription_entitlement_service.apply_transition() every time a
    # paid transition (fresh/renewal/upgrade/downgrade/trial_convert)
    # writes this row. Null for a trial period (no Order exists yet) and
    # for any Subscription row created before this column existed.
    #
    # This is what makes upgrade proration possible: without a link back
    # to the actual amount paid, there's no way to tell "what did this
    # shop really pay for their current Base period" (which may be less
    # than Plan.price_paise if a coupon was used) — see
    # subscription_entitlement_service.compute_upgrade_credit_paise().
    # Nullable and always read defensively (falls back to zero credit)
    # so old rows never crash the upgrade path.
    funding_order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)