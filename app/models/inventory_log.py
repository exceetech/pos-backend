from sqlalchemy import Column, Integer, Float, String, ForeignKey, DateTime, Boolean
from datetime import datetime
from app.database import Base
from app.util.time_utils import local_now

class InventoryLog(Base):
    __tablename__ = "inventory_logs"

    id = Column(Integer, primary_key=True)

    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("shop_products.id"), nullable=False)

    type = Column(String, nullable=False)  # ADD, SALE, LOSS, RETURN, PURCHASE_RETURN, ADJUST, CANCEL_RESTOCK

    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)

    created_at = Column(DateTime, default=local_now)

    is_active = Column(Boolean, default=True)

    # Stable client idempotency key ("<device_id>:<local_log_id>"). Lets a
    # retried inventory push dedupe exactly instead of relying on the fragile
    # content+timestamp match (Sync audit S2).
    client_uid = Column(String, nullable=True, index=True)