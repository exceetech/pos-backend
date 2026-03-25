from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from app.database import Base


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)

    shop_id = Column(Integer, ForeignKey("shops.id"))

    plan = Column(String)  # monthly / yearly

    start_date = Column(DateTime)
    expiry_date = Column(DateTime)

    status = Column(String, default="active")