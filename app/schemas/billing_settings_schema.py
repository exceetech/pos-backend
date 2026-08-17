from pydantic import BaseModel


class BillingSettingsResponse(BaseModel):
    default_gst: float
    printer_layout: str
    # key_secret / webhook_secret are deliberately NEVER returned — only
    # the public key_id (safe, Razorpay shows it on the shop's own
    # invoices too) plus a computed "is it set up" flag so the app can
    # show a connected/not-connected state without ever re-displaying
    # the secret.
    razorpay_key_id: str | None = None
    razorpay_configured: bool = False


class BillingSettingsUpdate(BaseModel):
    default_gst: float
    printer_layout: str
    # All three optional and write-only: omitting them (None) leaves
    # whatever is already saved untouched, so re-saving printer_layout
    # from the existing settings screen can never accidentally wipe a
    # shop's already-connected Razorpay credentials.
    razorpay_key_id: str | None = None
    razorpay_key_secret: str | None = None
    razorpay_webhook_secret: str | None = None