# models/purchase_return.py
"""
Purchase return — stock returned to a supplier.

Mirrors the local Room entity in
`com.example.easy_billing.db.PurchaseReturn` 1:1 so the sync push
is a straight column-for-column copy. Indexed by (shop_id) for
the per-shop list endpoints and by (hsn_code) for HSN-grouped
reports.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Index
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
