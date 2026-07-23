from sqlalchemy import Column, Integer, Float, DateTime, ForeignKey, String
from datetime import datetime
from app.database import Base
from app.util.time_utils import local_now

class SaleItem(Base):
    __tablename__ = "sale_items"

    id = Column(Integer, primary_key=True)

    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False)
    product_id = Column(Integer, nullable=False)

    # 🔥 IMPORTANT (store name for grouping)
    product_name = Column(String, nullable=False)
    variant = Column(String, nullable=True)
    
    # Link to the original bill so cancellations can delete the analytics rows
    bill_number = Column(String, nullable=True, index=True)

    # Idempotency key (Report 5 fix): mirrors Bill.client_bill_id /
    # Bill.client_device_id. /sales/create used to be fire-and-forget with
    # no retry and no dedupe — a retried or backfilled push must not create
    # a second batch of rows for the same local sale.
    client_bill_id = Column(Integer, nullable=True, index=True)
    client_device_id = Column(String, nullable=True)

    quantity = Column(Float, nullable=False)

    selling_price = Column(Float, nullable=False)
    cost_price = Column(Float, nullable=False)

    total_revenue = Column(Float, nullable=False)
    total_cost = Column(Float, nullable=False)

    created_at = Column(DateTime, default=local_now)