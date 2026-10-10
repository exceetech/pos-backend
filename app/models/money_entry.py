"""
Payment & cash-flow tracking: the Money Book (mirror of the app's `money_entries` table).

One row per real movement of money (direction IN/OUT, mode CASH/UPI/CARD/BANK).
Append-only: an amount is never edited; a refund or a mistake is a new opposite row.
The only field that changes after the first push is `status` (PENDING -> RECEIVED when a UPI
payment link is paid) plus the descriptive `party_name` / `ref_text`.

Idempotent on (shop_id, uid): `uid` is a random id made by the app that never repeats across
phones or reinstalls, so a retried push can never write a row twice.
"""
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, UniqueConstraint, Index
from app.database import Base
from app.models.money_type import MONEY
from app.util.time_utils import local_now


class MoneyEntry(Base):
    __tablename__ = "money_entries"
    __table_args__ = (
        UniqueConstraint("shop_id", "uid", name="uq_money_entry_shop_uid"),
        Index("ix_money_entries_shop_created", "shop_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False, index=True)
    uid = Column(String(40), nullable=False)
    # Random id of the app install that wrote the row (informational) and its local row id.
    origin = Column(String(40), nullable=False, default="", server_default="")
    local_id = Column(Integer, nullable=False, default=0, server_default="0")

    direction = Column(String(3), nullable=False)          # IN | OUT
    mode = Column(String(8), nullable=False)               # CASH | UPI | CARD | BANK
    amount = Column(MONEY, nullable=False)                 # always positive
    reason = Column(String(24), nullable=False)

    source_type = Column(String(24), nullable=False)       # BILL | CREDIT_NOTE | ... | MANUAL
    source_id = Column(Integer, nullable=False, default=0)  # raw local id on the origin device
    parent_type = Column(String(24), nullable=False)
    parent_id = Column(Integer, nullable=False, default=0)

    party_name = Column(String(120), nullable=False, default="", server_default="")
    ref_text = Column(String(60), nullable=False, default="", server_default="")   # bill / purchase number
    status = Column(String(10), nullable=False, default="RECEIVED")                 # RECEIVED | PENDING

    created_at = Column(DateTime, nullable=False, default=local_now)
