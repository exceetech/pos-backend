from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Boolean
from sqlalchemy.sql import func
from app.database import Base
from app.util.time_utils import local_now


class CreditAccount(Base):
    __tablename__ = "credit_accounts"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, nullable=False)
    phone = Column(String, nullable=False, index=True)

    due_amount = Column(Float, default=0.0)

    shop_id = Column(Integer, nullable=False, index=True)  # 🔥 MULTI-SHOP

    created_at = Column(DateTime, default=local_now)
    is_active = Column(Boolean, default=True)


class CreditTransaction(Base):
    __tablename__ = "credit_transactions"

    id = Column(Integer, primary_key=True, index=True)

    account_id = Column(Integer, ForeignKey("credit_accounts.id"), nullable=False)

    shop_id = Column(Integer, nullable=False, index=True)  # 🔥 ADD THIS

    amount = Column(Float, nullable=False)
    type = Column(String, nullable=False)  # ADD / PAY / SETTLE / PURCHASE_CREDIT / PURCHASE_RETURN / WRITE_OFF / REFUND / SALE_RETURN / BILL_CANCEL / DEBIT_NOTE
    reference_invoice = Column(String, nullable=True)

    # Idempotency key (duplicate-txn guard): a stable identifier the client
    # derives per source event (e.g. "CN:12", "PBUY:5", "BILL_CANCEL:41").
    # /credit/sync dedupes on (shop_id, source_doc) so a retried sync after a
    # lost HTTP response can't double-apply the balance delta. Nullable so
    # older app builds that don't send it keep working through the rollover.
    source_doc = Column(String, nullable=True)

    created_at = Column(DateTime, default=local_now)