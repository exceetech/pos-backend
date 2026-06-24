from sqlalchemy import Column, Integer, Float, String, ForeignKey, DateTime, Boolean
from datetime import datetime
from app.database import Base
from app.util.time_utils import local_now, utc_now
from app.models.money_type import MONEY  # R3: exact decimal for money

class Bill(Base):
    __tablename__ = "bills"

    id = Column(Integer, primary_key=True, index=True)

    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False)

    bill_number = Column(String, unique=True, index=True, nullable=False)

    # ── Financial Summaries ──
    # R3: MONEY = Numeric(12,2, asdecimal=False) — exact in DB, float in Python
    subtotal = Column(MONEY, nullable=False, default=0.0)
    discount_amount = Column(MONEY, nullable=False, default=0.0)
    taxable_amount = Column(MONEY, nullable=False, default=0.0)

    cgst_amount = Column(MONEY, nullable=False, default=0.0)
    sgst_amount = Column(MONEY, nullable=False, default=0.0)
    igst_amount = Column(MONEY, nullable=False, default=0.0)
    cess_amount = Column(MONEY, nullable=False, default=0.0)
    gst_amount = Column(MONEY, nullable=False, default=0.0)

    round_off = Column(MONEY, nullable=False, default=0.0)
    final_amount = Column(MONEY, nullable=False, default=0.0)
    
    # Removed legacy fields: total_amount, gst, discount

    total_items = Column(Float, nullable=False, default=0.0)
    payment_method = Column(String, nullable=False, default="Cash")

    # ── GST Meta Data ──
    gst_scheme = Column(String, nullable=False, default="Regular")
    supply_type = Column(String, nullable=False, default="intrastate")
    customer_state = Column(String, nullable=True)
    customer_state_code = Column(String, nullable=True)
    invoice_type = Column(String, nullable=False, default="B2C")
    is_gst_invoice = Column(Boolean, nullable=False, default=False)

    # ── Idempotency key (duplicate-bill guard) ──
    # The app's local Room bill id + device id. /bills/create refuses to
    # insert a second row for the same (shop, device, local bill), so a
    # retried or concurrent sync can never duplicate a sale.
    client_bill_id = Column(Integer, nullable=True, index=True)
    client_device_id = Column(String, nullable=True)

    # ── Cancellation (void) ──
    # `active` stays the single "include in reports" switch (all report
    # queries filter active == True). is_cancelled records WHY a bill is
    # inactive: voided invoice vs. clear-bills archive.
    is_cancelled = Column(Boolean, nullable=False, default=False)
    cancelled_at = Column(DateTime, nullable=True)

    active = Column(Boolean, default=True)

    # H6: default in app timezone (matches device-supplied timestamps)
    created_at = Column(DateTime, default=local_now)

    # Server-set, auto-bumped on every ORM update (e.g. cancellation flips
    # is_cancelled) — a monotonic cursor for pulling cancellations to other
    # terminals (Sync re-audit, bill-cancellation propagation). Uses UTC so the
    # cursor is comparable regardless of the app timezone.
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)