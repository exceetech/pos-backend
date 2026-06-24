from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from datetime import datetime
from app.database import Base
from app.util.time_utils import local_now, utc_now

class PurchaseImportDetails(Base):
    __tablename__ = "purchase_import_details"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False, index=True)
    purchase_id = Column(Integer, ForeignKey("purchases.id"), nullable=True, index=True)
    
    local_id = Column(Integer, nullable=True, index=True)
    local_purchase_id = Column(Integer, nullable=True, index=True)
    
    port_code = Column(String, nullable=False)
    bill_of_entry_number = Column(String, nullable=False, index=True)
    bill_of_entry_date = Column(DateTime, nullable=False)
    bill_of_entry_value = Column(Float, nullable=False, default=0.0)
    document_type = Column(String, nullable=False, default="Bill of Entry")
    sez_supplier_gstin = Column(String, nullable=True)
    
    sync_status = Column(String, nullable=False, default="synced")
    device_id = Column(String, nullable=True)
    
    created_at = Column(DateTime, default=local_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
