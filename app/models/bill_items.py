from sqlalchemy import Column, Integer, ForeignKey, Float, String, DateTime
from app.database import Base
from datetime import datetime

class BillItem(Base):
    __tablename__ = "bill_items"

    id = Column(Integer, primary_key=True, index=True)

    bill_id = Column(Integer, ForeignKey("bills.id"), nullable=False, index=True)
    shop_product_id = Column(Integer, ForeignKey("shop_products.id"), nullable=False, index=True)

    product_name = Column(String, nullable=False)
    quantity = Column(Float, nullable=False)
    unit = Column(String, nullable=False, default="unit")
    variant = Column(String, nullable=True)
    price = Column(Float, nullable=False)
    subtotal = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)