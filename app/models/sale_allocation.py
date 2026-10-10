"""
Stage 3D: exact sales allocations, price-correction write-off pools and
customer-return claims (mirror of the app's Room tables).

All three are idempotent on (shop_id, local_id): the app pushes its local row
id and the server upserts. Product / purchase ids are SERVER ids, bills are
identified by bill_number + line ordinal, so a reinstall can rebuild the links.
"""
from sqlalchemy import Column, Integer, Float, String, ForeignKey, DateTime, UniqueConstraint
from app.database import Base
from app.util.time_utils import local_now


class SaleBatchAllocation(Base):
    __tablename__ = "sale_batch_allocations"
    __table_args__ = (UniqueConstraint("shop_id", "origin", "local_id", name="uq_sale_alloc_shop_origin_local"),)

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False, index=True)
    # Random id of the app install that wrote the row, so a reinstall / wipe that
    # restarts local ids at 1 can never overwrite older rows.
    origin = Column(String(40), nullable=False, default="", server_default="")
    local_id = Column(Integer, nullable=False)

    source_type = Column(String(24), nullable=False)       # SALE | SALES_DEBIT_NOTE | SCRAP | LOSS | CLEAR
    source_id = Column(Integer, nullable=False, default=0)  # raw local id on the origin device
    bill_number = Column(String, nullable=True, index=True)
    line_ordinal = Column(Integer, nullable=True)           # n-th line of that product on the bill

    product_id = Column(Integer, nullable=False, index=True)             # server product id
    purchase_invoice_id = Column(Integer, nullable=True, index=True)     # server purchase id (null = unallocated)
    batch_local_id = Column(Integer, nullable=True)

    quantity = Column(Float, nullable=False)
    quantity_restored = Column(Float, nullable=False, default=0.0)
    unit_cost_net = Column(Float, nullable=False, default=0.0)
    unit_cost_gross = Column(Float, nullable=False, default=0.0)

    created_at = Column(DateTime, default=local_now)


class PdnGonePool(Base):
    __tablename__ = "pdn_gone_pools"
    __table_args__ = (UniqueConstraint("shop_id", "origin", "local_id", name="uq_pdn_pool_shop_origin_local"),)

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False, index=True)
    # Random id of the app install that wrote the row, so a reinstall / wipe that
    # restarts local ids at 1 can never overwrite older rows.
    origin = Column(String(40), nullable=False, default="", server_default="")
    local_id = Column(Integer, nullable=False)

    note_local_id = Column(Integer, nullable=False)
    purchase_invoice_id = Column(Integer, nullable=False, index=True)    # server purchase id
    product_id = Column(Integer, nullable=False)                         # server product id
    gone_qty = Column(Float, nullable=False)
    delta_gross = Column(Float, nullable=False)
    note_date = Column(DateTime, nullable=False)


class CostCorrectionClaim(Base):
    __tablename__ = "cost_correction_claims"
    __table_args__ = (UniqueConstraint("shop_id", "origin", "local_id", name="uq_cost_claim_shop_origin_local"),)

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False, index=True)
    # Random id of the app install that wrote the row, so a reinstall / wipe that
    # restarts local ids at 1 can never overwrite older rows.
    origin = Column(String(40), nullable=False, default="", server_default="")
    local_id = Column(Integer, nullable=False)

    allocation_local_id = Column(Integer, nullable=False)
    pool_local_id = Column(Integer, nullable=False)
    note_local_id = Column(Integer, nullable=False)
    product_id = Column(Integer, nullable=True, index=True)              # server product id (for per-product profit)

    qty = Column(Float, nullable=False)
    # profit-VARIANCE sign: positive = loss, negative = gain
    amount = Column(Float, nullable=False)
    claim_date = Column(DateTime, nullable=False, index=True)
    source_type = Column(String(16), nullable=False)                     # SALES_RETURN | BILL_CANCEL
    source_id = Column(Integer, nullable=False, default=0)
    # Bill the pens were sold on, so claims of archived (cleared) bills can be left out of profit.
    bill_number = Column(String, nullable=True, index=True)
