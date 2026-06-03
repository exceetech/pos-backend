# models/purchase_return.py
"""
Purchase return — stock returned to a supplier.

Mirrors the local Room entity in
`com.example.easy_billing.db.PurchaseReturn` 1:1 so the sync push
is a straight column-for-column copy. Indexed by (shop_id) for
the per-shop list endpoints and by (hsn_code) for HSN-grouped
reports.
"""

from sqlalchemy import BigInteger, Column, Integer, String, Float, DateTime, ForeignKey, Index
from datetime import datetime
from app.database import Base


class PurchaseReturn(Base):
    __tablename__ = "purchase_returns"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False, index=True)

    # Optional FK to the shop_product for joinable reports — left
    # nullable because offline rows may not yet have a server id
    # for the product when they're pushed.
    shop_product_id = Column(Integer, ForeignKey("shop_products.id"), nullable=True)

    product_name = Column(String, nullable=False)
    variant_name = Column(String, nullable=True)
    hsn_code = Column(String, nullable=True, index=True)

    quantity_returned = Column(Float, nullable=False)
    taxable_amount = Column(Float, nullable=False, default=0.0)

    cgst_percentage = Column(Float, default=0.0)
    sgst_percentage = Column(Float, default=0.0)
    igst_percentage = Column(Float, default=0.0)

    cgst_amount = Column(Float, default=0.0)
    sgst_amount = Column(Float, default=0.0)
    igst_amount = Column(Float, default=0.0)

    state = Column(String, nullable=False, default="")
    invoice_value = Column(Float, nullable=False, default=0.0)

    supplier_gstin = Column(String, nullable=True)
    supplier_name = Column(String, nullable=True)

    # Return-on-credit fields.
    is_credit = Column(Integer, nullable=False, default=0)
    credit_account_id = Column(Integer, ForeignKey("credit_accounts.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # ── Debit/Credit Note fields (v25+) ──────────────────────────────────
    #
    # All nullable so existing rows remain valid.

    # Auto-generated sequential note number, e.g. "DN-00001" or "CN-00001".
    note_number = Column(String, nullable=True, index=True)

    # Epoch millis when this note was raised.
    note_date = Column(BigInteger, nullable=True)

    # "D" for Debit Note, "C" for Credit Note.
    note_type = Column(String(1), nullable=True)

    # Soft pointer back to the purchase invoice — NOT a FK (offline-first).
    original_invoice_id     = Column(Integer, nullable=True, index=True)
    original_invoice_number = Column(String, nullable=True)
    original_invoice_date   = Column(BigInteger, nullable=True)

    # GST fields required for GSTR-2 / CDN reporting.
    place_of_supply = Column(String, nullable=True)
    supply_type     = Column(String, nullable=True, default="intrastate")
    cess_amount     = Column(Float, nullable=True, default=0.0)
    tax_amount      = Column(Float, nullable=True, default=0.0)
    total_amount    = Column(Float, nullable=True, default=0.0)

    document_type   = Column(String, nullable=True)
    document_nature = Column(String, nullable=True)
    document_series = Column(String, nullable=True)

    pre_gst = Column(String, nullable=False, default="N")
    reason_for_issuing_document = Column(String, nullable=False, default="Purchase return")
    note_refund_voucher_value = Column(Float, nullable=False, default=0.0)
    rate = Column(Float, nullable=False, default=0.0)
    eligibility_for_itc = Column(String, nullable=False, default="Inputs")
    availed_itc_integrated_tax = Column(Float, nullable=False, default=0.0)
    availed_itc_central_tax = Column(Float, nullable=False, default=0.0)
    availed_itc_state_tax = Column(Float, nullable=False, default=0.0)
    availed_itc_cess = Column(Float, nullable=False, default=0.0)
    invoice_type = Column(String, nullable=False, default="Regular")
    place_of_supply_code = Column(String, nullable=False, default="")
