from sqlalchemy import Boolean, Column, Integer, String, DateTime
from datetime import datetime
from app.database import Base

class Shop(Base):
    __tablename__ = "shops"

    id = Column(Integer, primary_key=True, index=True)
    shop_name = Column(String, nullable=False)
    owner_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True)
    phone = Column(String)
    password_hash = Column(String, nullable=True)
    status = Column(String, default="PENDING")
    is_first_login = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)