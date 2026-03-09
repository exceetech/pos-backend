from sqlalchemy import Column, Integer, Float, String, ForeignKey, DateTime, Boolean
from datetime import datetime
from app.database import Base
from datetime import datetime

class Bill(Base):
    __tablename__ = "bills"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id"))

    bill_number = Column(String, unique=True, index=True)

    total_amount = Column(Float)
    total_items = Column(Integer)
    payment_method = Column(String)
    gst = Column(Float)
    discount = Column(Float)

    active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.now)