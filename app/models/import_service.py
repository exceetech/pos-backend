from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from datetime import datetime
from app.database import Base
from app.util.time_utils import local_now, utc_now

class ImportService(Base):
    __tablename__ = "import_services"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False, index=True)
    local_id = Column(Integer, nullable=True, index=True)

    invoice_number = Column(String, nullable=False, index=True)
    invoice_date = Column(DateTime, nullable=False)
    invoice_value = Column(Float, nullable=False, default=0.0)
    place_of_supply = Column(String, nullable=False)

    rate = Column(Float, nullable=False, default=0.0)
    taxable_value = Column(Float, nullable=False, default=0.0)
    igst_paid = Column(Float, nullable=False, default=0.0)
    cess_paid = Column(Float, nullable=False, default=0.0)
    
    eligibility_for_itc = Column(String, nullable=False, default="Inputs")
    availed_itc_igst = Column(Float, nullable=False, default=0.0)
    availed_itc_cess = Column(Float, nullable=False, default=0.0)

    sync_status = Column(String, nullable=False, default="synced")
    device_id = Column(String, nullable=True)

    created_at = Column(DateTime, default=local_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
