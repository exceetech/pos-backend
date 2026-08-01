from sqlalchemy import Column, Integer, String, DateTime, Float
from app.database import Base
from app.util.time_utils import utc_now


class AuditLog(Base):
    """
    Append-only trail for subscription/payment state changes — plan §6
    ("audit logging on every state change... not for the payment flow to
    depend on, but so that when a customer disputes 'I paid but wasn't
    activated' six months from now, you have a trail instead of a
    shrug"). Deliberately NOT read by any business logic — this table
    only ever gets written to and queried by a human/support tool later.
    """
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)

    shop_id = Column(Integer, nullable=True, index=True)
    event_type = Column(String, nullable=False, index=True)
    # Free-text summary — kept simple (not a JSON blob needing a schema)
    # since this is read by a human during a support investigation, not
    # parsed programmatically.
    detail = Column(String, nullable=True)
    amount_paise = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=utc_now, index=True)
