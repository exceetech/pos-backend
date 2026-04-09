from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Boolean
from sqlalchemy.sql import func
from app.database import Base


class CreditAccount(Base):
    __tablename__ = "credit_accounts"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, nullable=False)
    phone = Column(String, nullable=False, index=True)

    due_amount = Column(Float, default=0.0)

    shop_id = Column(Integer, nullable=False, index=True)  # 🔥 MULTI-SHOP

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)


class CreditTransaction(Base):
    __tablename__ = "credit_transactions"

    id = Column(Integer, primary_key=True, index=True)

    account_id = Column(Integer, ForeignKey("credit_accounts.id"), nullable=False)

    shop_id = Column(Integer, nullable=False, index=True)  # 🔥 ADD THIS

    amount = Column(Float, nullable=False)
    type = Column(String, nullable=False)  # ADD / PAY / SETTLE

    created_at = Column(DateTime(timezone=True), server_default=func.now())