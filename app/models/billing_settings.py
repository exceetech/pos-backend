from sqlalchemy import Column, Integer, Float, String, ForeignKey
from app.database import Base


class BillingSettings(Base):

    __tablename__ = "billing_settings"

    id = Column(Integer, primary_key=True, index=True)

    shop_id = Column(Integer, ForeignKey("shops.id"), unique=True)

    default_gst = Column(Float, default=0)

    printer_layout = Column(String, default="80mm")

    # ── Per-shop Razorpay account (v52) ─────────────────────────────────
    # Each shop connects its OWN Razorpay account so "send to customer"
    # UPI payment links deposit directly into that shop's own bank
    # account — never a shared/platform account. key_id is safe to
    # display back to the shop (it's the public identifier Razorpay
    # itself shows on invoices); key_secret and webhook_secret are
    # write-only from the API's perspective — see BillingSettingsResponse,
    # which deliberately omits both.
    razorpay_key_id = Column(String, nullable=True)
    razorpay_key_secret = Column(String, nullable=True)
    # Set by the shop from THEIR OWN Razorpay dashboard's webhook config —
    # each shop's account needs its own webhook pointed at
    # POST /pos-payments/webhook with this same secret, since Razorpay
    # signs each account's webhook deliveries with that account's own
    # secret. See pos_payment_routes.webhook for how the right shop's
    # secret gets picked before verifying.
    razorpay_webhook_secret = Column(String, nullable=True)