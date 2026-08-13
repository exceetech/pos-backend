from sqlalchemy import Column, Integer, Float, ForeignKey, Boolean, DateTime
from datetime import datetime
from app.database import Base
from app.util.time_utils import utc_now

class Inventory(Base):
    __tablename__ = "inventory"

    product_id = Column(Integer, ForeignKey("shop_products.id"), primary_key=True)
    # Also part of the composite primary key (so it's already indexed as
    # the PK's second column), but explicitly indexed too — queries that
    # filter by shop_id alone (e.g. "list this shop's whole inventory")
    # don't benefit from a composite index unless the filtered column is
    # its leading member, which shop_id isn't here.
    shop_id = Column(Integer, ForeignKey("shops.id"), primary_key=True, index=True)

    current_stock = Column(Float, default=0.0)
    average_cost = Column(Float, default=0.0)

    is_active = Column(Boolean, default=True)

    # Server-set, auto-bumped on every ORM update — the delta-pull cursor
    # (Sync audit S5). onupdate fires for any session flush of a dirty row,
    # so all ORM write paths are covered without per-route changes.
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)