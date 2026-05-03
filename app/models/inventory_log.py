from sqlalchemy import Column, Integer, Float, String, ForeignKey, DateTime, Boolean
from datetime import datetime
from app.database import Base

class InventoryLog(Base):
    __tablename__ = "inventory_logs"

    id = Column(Integer, primary_key=True)

    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("shop_products.id"), nullable=False)

    type = Column(String, nullable=False)  # ADD, SALE, LOSS, ADJUST

    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    is_active = Column(Boolean, default=True)