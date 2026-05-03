from sqlalchemy import Column, Integer, Float, Boolean, ForeignKey, String
from app.database import Base

class ShopProduct(Base):
    __tablename__ = "shop_products"

    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False)
    global_product_id = Column(Integer, ForeignKey("global_products.id"), nullable=False)

    variant_name = Column(String, nullable=True)
    unit = Column(String, default="unit")

    price = Column(Float, nullable=False)
    is_active = Column(Boolean, default=True)

    # GST fields
    hsn_code = Column(String, nullable=True)
    default_gst_rate = Column(Float, default=0.0)