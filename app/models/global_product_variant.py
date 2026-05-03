from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from app.database import Base


class GlobalProductVariant(Base):
    __tablename__ = "global_product_variants"

    id = Column(Integer, primary_key=True, index=True)

    product_id = Column(Integer, ForeignKey("global_products.id"), nullable=False)

    variant_name = Column(String, nullable=False)
    unit = Column(String, default="unit")

    is_verified = Column(Boolean, default=False)