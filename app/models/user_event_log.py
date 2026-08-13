from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from app.database import Base
from app.util.time_utils import utc_now


class UserEventLog(Base):
    """
    A lightweight breadcrumb trail of what a shop actually did in the app —
    screens opened, buttons tapped, validation failures, sync/exception
    errors. Not analytics: this exists so that when a shop reports "this is
    broken," support can pull up their recent events and see whether they
    followed the right steps (a real bug) or hit an expected validation
    error (a user mistake), instead of guessing from a vague bug report.

    Deliberately NOT storing raw sensitive input (passwords, OTPs, tokens,
    full card/GSTIN values) — `detail` should describe the event
    ("otp_invalid", "quantity_exceeds_stock") not the raw value that
    triggered it.

    Retention: kept for 90 days, auto-deleted after that by a daily
    scheduled job (see app/services/event_log_cleanup_service.py). Admin
    can also delete on demand (per shop_id or by id) — see
    app/routes/user_event_log_routes.py.
    """
    __tablename__ = "user_event_logs"

    id = Column(Integer, primary_key=True, index=True)

    # Indexed — every lookup for a support investigation filters by
    # shop_id, and the daily cleanup job filters by created_at.
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False, index=True)

    # e.g. "screen_opened", "action_tapped", "validation_failed", "error"
    event_type = Column(String, nullable=False)

    # e.g. "InventoryActivity", "ConfirmPaymentActivity" — which screen
    # this happened on, so a support read-through can follow the flow.
    screen = Column(String, nullable=True)

    # Short, non-sensitive detail — a category/code, not raw user input.
    # e.g. "quantity_exceeds_stock", "gstin_invalid", "sync_failed: purchases"
    detail = Column(Text, nullable=True)

    created_at = Column(DateTime, default=utc_now, nullable=False, index=True)
