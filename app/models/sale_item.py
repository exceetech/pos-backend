from sqlalchemy import Column, Integer, Float, DateTime, ForeignKey, String
from datetime import datetime
from app.database import Base

class SaleItem(Base):
    __tablename__ = "sale_items"

    id = Column(Integer, primary_key=True)

    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False)
    product_id = Column(Integer, nullable=False)

    # 🔥 IMPORTANT (store name for grouping)
    product_name = Column(String, nullable=False)
    variant = Column(String, nullable=True)

    quantity = Column(Float, nullable=False)

    selling_price = Column(Float, nullable=False)
    cost_price = Column(Float, nullable=False)

    total_revenue = Column(Float, nullable=False)
    total_cost = Column(Float, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)