import uuid
from sqlalchemy import Column, String, DateTime, Integer, ForeignKey
from datetime import datetime
from app.database import Base


def _uuid():
    return str(uuid.uuid4())


class StoreGstProfile(Base):
    __tablename__ = "store_gst_profile"

    id = Column(String, primary_key=True, default=_uuid)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False, unique=True, index=True)

    gstin = Column(String, nullable=False)

    legal_name = Column(String, default="")
    trade_name = Column(String, default="")
    gst_scheme = Column(String, default="")
    registration_type = Column(String, default="")
    state_code = Column(String, default="")

    address = Column(String, default="")

    sync_status = Column(String, default="pending")
    device_id = Column(String, default="")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)