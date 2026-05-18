import uuid
from sqlalchemy import Column, String, Float, DateTime, Integer, ForeignKey
from datetime import datetime
from app.database import Base


def _uuid():
    return str(uuid.uuid4())


class GstPurchaseRecord(Base):
    """
    One record per purchase invoice / expense entry with GST breakdown.
    Used for GSTR-2 (purchase register) and GSTR-3B ITC computation.
    """
    __tablename__ = "gst_purchase_records"

    id = Column(String, primary_key=True, default=_uuid)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False, index=True)

    # Supplier
    supplier_gstin = Column(String, nullable=True)

    # Invoice
    invoice_number = Column(String, nullable=False, index=True)
    invoice_date = Column(DateTime, nullable=False, index=True)

    # Classification
    expense_type = Column(String, nullable=False)   # STOCK / EXPENSE / SERVICE
    hsn_sac_code = Column(String, nullable=False)
    description = Column(String, default="")

    # Tax
    taxable_value = Column(Float, nullable=False)
    gst_rate = Column(Float, nullable=False)
    cgst_amount = Column(Float, default=0.0)
    sgst_amount = Column(Float, default=0.0)
    igst_amount = Column(Float, default=0.0)
    total_amount = Column(Float, nullable=False)

    # Sync
    sync_status = Column(String, default="pending")   # pending / synced / failed
    device_id = Column(String, default="")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
