from sqlalchemy import Column, Integer, Float, ForeignKey, Boolean
from app.database import Base

class Inventory(Base):
    __tablename__ = "inventory"

    product_id = Column(Integer, ForeignKey("shop_products.id"), primary_key=True)
    shop_id = Column(Integer, ForeignKey("shops.id"), primary_key=True)

    current_stock = Column(Float, default=0.0)
    average_cost = Column(Float, default=0.0)

    is_active = Column(Boolean, default=True)