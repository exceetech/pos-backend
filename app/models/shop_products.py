from sqlalchemy import Column, Integer, Float, Boolean, ForeignKey
from app.database import Base

class ShopProduct(Base):
    __tablename__ = "shop_products"

    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False)
    global_product_id = Column(Integer, ForeignKey("global_products.id"), nullable=False)

    price = Column(Float, nullable=False)
    is_active = Column(Boolean, default=True)