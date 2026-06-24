from sqlalchemy import Column, Integer, String, Boolean, BigInteger, UniqueConstraint, DateTime
from sqlalchemy.sql import func
from app.database import Base
from app.util.time_utils import local_now


class Customer(Base):
    """
    Customer master, keyed by (shop_id, phone) (v40).

    Powers the phone-first lookup/auto-fill on the invoice screen for
    both B2B and B2C. The invoice still stores its own customer snapshot,
    so this table never affects billing/printing/GST — it is additive.

    Sync is upsert-by-(shop_id, phone): two devices that create the same
    phone offline converge to one row; field conflicts resolve by latest
    `updated_at_ms` (client epoch millis).
    """
    __tablename__ = "customers"
    __table_args__ = (
        # One record per (shop, phone, type): a customer may have BOTH a
        # B2C and a B2B entry under the same number.
        UniqueConstraint("shop_id", "phone", "customer_type", name="uix_customer_shop_phone_type"),
    )

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, nullable=False, index=True)

    phone = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False, default="")
    customer_type = Column(String, nullable=False, default="B2C")  # B2B / B2C

    business_name = Column(String, nullable=True)
    gstin = Column(String, nullable=True)
    state = Column(String, nullable=True)
    state_code = Column(String, nullable=True)

    credit_account_id = Column(Integer, nullable=True)

    is_active = Column(Boolean, default=True)

    updated_at_ms = Column(BigInteger, default=0)
    created_at = Column(DateTime, default=local_now)
