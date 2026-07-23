# models/scrap.py
"""
Scrap / expired stock write-off.

Same shape as PurchaseReturn (per spec) — both feed identical
reporting / accounting pipelines but live in distinct tables so
the row-level intent stays clear.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from datetime import datetime
from app.database import Base
from app.util.time_utils import local_now


class Scrap(Base):
    __tablename__ = "scrap_entries"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False, index=True)

    # Idempotency key: the client's local Room scrap_table.id. Lets
    # /scrap/sync dedupe a retried/duplicate offline push on
    # (shop_id, local_id) instead of inserting a second row every time
    # the response is lost after the server already committed it.
    local_id = Column(Integer, nullable=True, index=True)

    shop_product_id = Column(Integer, ForeignKey("shop_products.id"), nullable=True)

    product_name = Column(String, nullable=False)
    variant_name = Column(String, nullable=True)
    hsn_code = Column(String, nullable=True, index=True)

    quantity = Column(Float, nullable=False)
    taxable_amount = Column(Float, nullable=False, default=0.0)

    cgst_percentage = Column(Float, default=0.0)
    sgst_percentage = Column(Float, default=0.0)
    igst_percentage = Column(Float, default=0.0)

    cgst_amount = Column(Float, default=0.0)
    sgst_amount = Column(Float, default=0.0)
    igst_amount = Column(Float, default=0.0)

    state = Column(String, nullable=False, default="")
    invoice_value = Column(Float, nullable=False, default=0.0)

    reason = Column(String, nullable=False, default="Scrap")

    created_at = Column(DateTime, default=local_now, nullable=False)
