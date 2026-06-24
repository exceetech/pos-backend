# models/purchase.py

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from datetime import datetime
from app.database import Base
from app.util.time_utils import local_now, utc_now


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

    # Date printed on the supplier's invoice — distinct from
    # `created_at` (when the row was inserted). Nullable so
    # existing rows that pre-date this column stay valid.
    invoice_date = Column(DateTime, nullable=True)

    # Purchase-on-credit fields. Both nullable for legacy rows.
    is_credit = Column(Integer, nullable=False, default=0)
    credit_account_id = Column(Integer, ForeignKey("credit_accounts.id"), nullable=True)

    local_id = Column(Integer, nullable=True, index=True)
    place_of_supply_code = Column(String, nullable=False, default="")
    reverse_charge = Column(String, nullable=False, default="N")
    invoice_type = Column(String, nullable=False, default="Regular")
    supply_type = Column(String, nullable=False, default="intrastate")
    cess_paid = Column(Float, nullable=False, default=0.0)
    eligibility_for_itc = Column(String, nullable=False, default="Inputs")
    availed_itc_integrated_tax = Column(Float, nullable=False, default=0.0)
    availed_itc_central_tax = Column(Float, nullable=False, default=0.0)
    availed_itc_state_tax = Column(Float, nullable=False, default=0.0)
    availed_itc_cess = Column(Float, nullable=False, default=0.0)
    purchase_source = Column(String, nullable=False, default="DOMESTIC")

    created_at = Column(DateTime, default=local_now)

    # Server-set, auto-bumped on every ORM update — delta-pull cursor (S5).
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)