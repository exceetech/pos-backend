from sqlalchemy import Column, Integer, Float, String, ForeignKey
from app.database import Base


class BillingSettings(Base):

    __tablename__ = "billing_settings"

    id = Column(Integer, primary_key=True, index=True)

    shop_id = Column(Integer, ForeignKey("shops.id"), unique=True)

    default_gst = Column(Float, default=0)

    printer_layout = Column(String, default="80mm")