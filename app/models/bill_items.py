from sqlalchemy import Column, Integer, ForeignKey, Float, String, DateTime
from sqlalchemy.sql import func
from app.database import Base
from datetime import datetime

class BillItem(Base):
    __tablename__ = "bill_items"

    id = Column(Integer, primary_key=True, index=True)

    bill_id = Column(Integer, ForeignKey("bills.id"), index=True)
    shop_product_id = Column(Integer, ForeignKey("shop_products.id"), index=True)

    product_name = Column(String)

    quantity = Column(Integer)
    price = Column(Float)

    subtotal = Column(Float)

    created_at = Column(DateTime, default=datetime.now)