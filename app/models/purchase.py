# models/purchase.py

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from datetime import datetime
from app.database import Base


class Purchase(Base):
    __tablename__ = "purchases"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False)

    invoice_number = Column(String, nullable=False, index=True)
    supplier_gstin = Column(String, nullable=True)
    supplier_name = Column(String, nullable=False)
    state = Column(String, nullable=False)

    taxable_amount = Column(Float, nullable=False)
    cgst_percentage = Column(Float, default=0.0)
    sgst_percentage = Column(Float, default=0.0)
    igst_percentage = Column(Float, default=0.0)

    cgst_amount = Column(Float, default=0.0)
    sgst_amount = Column(Float, default=0.0)
    igst_amount = Column(Float, default=0.0)

    invoice_value = Column(Float, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)