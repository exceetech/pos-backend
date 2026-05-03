from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from app.database import Base


class GlobalHSN(Base):
    __tablename__ = "global_hsn"

    id = Column(Integer, primary_key=True, index=True)

    hsn_code = Column(String, nullable=False)
    product_id = Column(Integer, ForeignKey("global_products.id"), nullable=False)

    is_verified = Column(Boolean, default=False)