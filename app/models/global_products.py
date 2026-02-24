from sqlalchemy import Column, Integer, String, Boolean
from app.database import Base

class GlobalProduct(Base):
    __tablename__ = "global_products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)

    is_verified = Column(Boolean, default=True)   # Admin approved
    created_by_shop_id = Column(Integer, nullable=True)