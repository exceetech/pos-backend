"""
Purchase batches — hybrid inventory model (v20+).

One row per *lot* added to stock. Powers two flows the legacy
weighted-average model could not handle correctly:
  • Supplier returns at the right per-batch unit cost.
  • FIFO consumption of remaining qty for scrap / expired /
    manual adjustments, while valuation continues to use the
    weighted average.

`unit_cost_excluding_tax` is always stored *without* GST so
reports never have to un-bake tax. Idempotent on `(shop_id, local_id)`.
"""

from sqlalchemy import Column, Integer, Float, String, ForeignKey, DateTime
from datetime import datetime
from app.database import Base
from app.util.time_utils import local_now


class PurchaseBatch(Base):
    __tablename__ = "purchase_batches"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False, index=True)

    # Echo of the client's local row id — used by the sync route to
    # idempotently upsert and to return a local_id → server_id map.
    local_id = Column(Integer, nullable=True, index=True)

    product_id = Column(Integer, nullable=True, index=True)
    purchase_invoice_id = Column(Integer, nullable=True, index=True)

    supplier_name = Column(String, nullable=True)
    supplier_gstin = Column(String, nullable=True)
    invoice_number = Column(String, nullable=True)
    batch_code = Column(String, nullable=True)

    quantity_purchased = Column(Float, nullable=False)
    quantity_remaining = Column(Float, nullable=False)

    unit_cost_excluding_tax = Column(Float, nullable=False, default=0.0)

    gst_percent = Column(Float, default=0.0)
    cgst_percent = Column(Float, default=0.0)
    sgst_percent = Column(Float, default=0.0)
    igst_percent = Column(Float, default=0.0)

    invoice_value = Column(Float, default=0.0)
    taxable_value = Column(Float, default=0.0)

    invoice_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=local_now)
