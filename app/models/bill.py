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

    # ── Customer-facing UPI payment link (v52) ──
    # Set when a "Send to customer" Razorpay Payment Link is created for
    # this bill. payment_status stays independent of payment_method above
    # — payment_method records how the SALE was recorded at checkout
    # (Cash/Card/UPI/Credit), while payment_status tracks whether the
    # SEPARATE customer-facing pay-later link has actually been paid.
    # "unpaid" is the default for every bill, including ones that never
    # get a link sent at all.
    payment_status = Column(String, nullable=False, default="unpaid")
    razorpay_payment_link_id = Column(String, nullable=True, index=True)
    razorpay_payment_link_url = Column(String, nullable=True)
    razorpay_payment_id = Column(String, nullable=True)

    # ── Customer-facing UPI QR code (v66) ──
    # Scan-to-pay in-person alternative to the payment link above — works
    # on any device (no SIM needed, nothing gets sent anywhere, the
    # screen just displays this). razorpay_qr_id is what the
    # "qr_code.credited" webhook is matched back against (QR codes don't
    # carry a reference_id the way Payment Links do). Whichever of the
    # QR or the link gets paid first, the other is auto-closed
    # server-side so the same bill can never be paid twice.
    razorpay_qr_id = Column(String, nullable=True, index=True)
    razorpay_qr_image_url = Column(String, nullable=True)
    # Epoch seconds Razorpay itself will auto-close this QR at (their own
    # `close_by`, echoed back on creation). create_qr must NOT reuse a
    # saved razorpay_qr_id past this moment — Razorpay has already killed
    # it server-side, so the cached image would be a dead code that can
    # never be scanned/paid again. (v67)
    razorpay_qr_close_by = Column(Integer, nullable=True)

    # ── GST Meta Data ──
    gst_scheme = Column(String, nullable=False, default="Regular")
    supply_type = Column(String, nullable=False, default="intrastate")
    customer_state = Column(String, nullable=True)
    customer_state_code = Column(String, nullable=True)
    invoice_type = Column(String, nullable=False, default="B2C")
    is_gst_invoice = Column(Boolean, nullable=False, default=False)

    # Server-side credit account this bill is charged to, if any (Report 1
    # S-2). Not a hard FK — mirrors the gst_sales_invoice.bill_id pattern —
    # since the client may push a bill before its credit account has synced
    # and received a server id. Lets server-side credit reconciliation and
    # cross-device restore attribute a bill to its account directly, instead
    # of relying only on credit_transactions.reference_invoice.
    credit_account_id = Column(Integer, nullable=True, index=True)

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