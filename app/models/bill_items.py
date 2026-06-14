from sqlalchemy import Column, Integer, ForeignKey, Float, String, DateTime
from app.database import Base
from datetime import datetime
from app.util.time_utils import local_now
from app.models.money_type import MONEY  # R3: exact decimal for money

class BillItem(Base):
    __tablename__ = "bill_items"

    id = Column(Integer, primary_key=True, index=True)

    bill_id = Column(Integer, ForeignKey("bills.id"), nullable=False, index=True)
    shop_product_id = Column(Integer, ForeignKey("shop_products.id"), nullable=False, index=True)

    product_name = Column(String, nullable=False)
    quantity = Column(Float, nullable=False, default=0.0)
    unit = Column(String, nullable=False, default="unit")
    variant = Column(String, nullable=True)
    
    # ── Item Financial Summaries ──
    # R3: amounts/prices are MONEY (exact); rates stay Float (percentages)
    unit_price = Column(MONEY, nullable=False, default=0.0)
    line_subtotal = Column(MONEY, nullable=False, default=0.0)
    discount_amount = Column(MONEY, nullable=False, default=0.0)
    taxable_amount = Column(MONEY, nullable=False, default=0.0)

    gst_rate = Column(Float, nullable=False, default=0.0)
    cgst_rate = Column(Float, nullable=False, default=0.0)
    sgst_rate = Column(Float, nullable=False, default=0.0)
    igst_rate = Column(Float, nullable=False, default=0.0)

    cgst_amount = Column(MONEY, nullable=False, default=0.0)
    sgst_amount = Column(MONEY, nullable=False, default=0.0)
    igst_amount = Column(MONEY, nullable=False, default=0.0)
    cess_amount = Column(MONEY, nullable=False, default=0.0)

    total_amount = Column(MONEY, nullable=False, default=0.0)
    
    hsn_code = Column(String, nullable=False, default="")

    # Removed legacy fields price, subtotal
    # H6: default in app timezone (matches device-supplied timestamps)
    created_at = Column(DateTime, default=local_now)