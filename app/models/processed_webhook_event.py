from sqlalchemy import Column, Integer, String, DateTime
from app.database import Base
from app.util.time_utils import utc_now


class ProcessedWebhookEvent(Base):
    """
    Dedup table for Razorpay webhook deliveries. Razorpay can and does
    resend the same event on retries; without this, a resent
    "payment.captured" event could double-activate a subscription or
    double-increment a coupon's usage count. The webhook handler checks
    for an existing row by razorpay_event_id before doing anything else,
    and only proceeds (and inserts this row) if it's genuinely new.
    """
    __tablename__ = "processed_webhook_events"

    id = Column(Integer, primary_key=True, index=True)

    razorpay_event_id = Column(String, unique=True, index=True, nullable=False)
    event_type = Column(String, nullable=True)
    processed_at = Column(DateTime, default=utc_now)  # Bucket B, see order.py
