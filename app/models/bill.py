from sqlalchemy import Column, Integer, Float, String, ForeignKey, DateTime, Boolean
from datetime import datetime
from app.database import Base

class Bill(Base):
    __tablename__ = "bills"

    id = Column(Integer, primary_key=True, index=True)

    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False)

    bill_number = Column(String, unique=True, index=True, nullable=False)

    total_amount = Column(Float, nullable=False)

    total_items = Column(Float, nullable=False)

    payment_method = Column(String, nullable=False)

    gst = Column(Float, default=0.0)
    discount = Column(Float, default=0.0)

    active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.now)