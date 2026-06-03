"""
GST-aware sales invoice (header + items).

Mirrors the Android pair `gst_sales_invoice_table` /
`gst_sales_items_table`. Sits *alongside* the existing
`bills` / `bill_items` tables (which are still the
canonical source of truth for bill history, reports and
inventory ops). The structures here exist so:

  • The mobile client can persist GST-aware metadata
    (B2B/B2C, scheme, customer GSTIN, per-line tax split)
    that has no clean home on the legacy schema.

  • GST reports / accountant exports can read from a
    flat schema that already carries everything the
    GSTR-1 / HSN summary path needs without joining
    five tables every time.

The relation back to the legacy bill is via `bill_id`,
which is *not* a hard FK — the offline-first client
generates rows before the bill exists on the server, and
we don't want batch sync to fail on missing parents.
"""
from sqlalchemy import Boolean, Column, Integer, Float, String, ForeignKey, DateTime, BigInteger, Index
from sqlalchemy.orm import relationship
from datetime import datetime

from app.database import Base


class GstSalesInvoice(Base):
    __tablename__ = "gst_sales_invoice"

    id = Column(Integer, primary_key=True, index=True)

    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False, index=True)

    # Soft pointer back to the legacy `bills` row. Not a FK on
    # purpose — the mobile client generates this before a bill
    # exists on the server, and we don't want sync to die on a
    # missing parent.
    bill_id = Column(Integer, nullable=True, index=True)

    # Echo of the client-side row id — lets the offline replay
    # path produce an idempotent {local_id → server_id} map.
    local_id = Column(Integer, nullable=True, index=True)

    invoice_type = Column(String, nullable=False, default="B2C")        # B2B / B2C
    gst_scheme = Column(String, nullable=False, default="")             # Composition Scheme / Normal GST Scheme

    customer_name = Column(String, nullable=True)
    business_name = Column(String, nullable=True)
    customer_phone = Column(String, nullable=True)
    customer_gst = Column(String, nullable=True)
    customer_state = Column(String, nullable=True)

    subtotal = Column(Float, nullable=False, default=0.0)
    total_cgst = Column(Float, nullable=False, default=0.0)
    total_sgst = Column(Float, nullable=False, default=0.0)
    total_igst = Column(Float, nullable=False, default=0.0)
    total_tax = Column(Float, nullable=False, default=0.0)
    grand_total = Column(Float, nullable=False, default=0.0)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # ── GSTR-1 fields (v23) ──────────────────────────────────────────

    # Human-readable bill / invoice number (e.g. "INV-0042").
    invoice_number = Column(String, nullable=True, default="")

    # Epoch millis — client clock at invoice creation time.
    invoice_date = Column(BigInteger, nullable=True, default=0)

    # "Y" = reverse charge applicable; "N" = not applicable (default).
    reverse_charge = Column(String, nullable=False, default="N")

    # GSTR-1 invoice type: Regular | SEZ supplies with payment |
    # SEZ supplies without payment | Deemed Exp
    gstr_invoice_type = Column(String, nullable=False, default="Regular")

    # 2-digit GST state code for Place of Supply (GSTR-1).
    customer_state_code = Column(String, nullable=True)

    # E-Commerce Operator GSTIN (only for e-commerce sales).
    ecommerce_gstin = Column(String, nullable=True)

    # E-Commerce Operator Name.
    ecommerce_operator_name = Column(String, nullable=True)

    # ── New ECO fields (Table 14/15) ──
    eco_nature_of_supply    = Column(String, nullable=True)
    eco_document_type       = Column(String, nullable=True)
    eco_supplier_gstin      = Column(String, nullable=True)
    eco_supplier_name       = Column(String, nullable=True)
    eco_recipient_gstin     = Column(String, nullable=True)
    eco_recipient_name      = Column(String, nullable=True)
    eco_role                = Column(String, nullable=True)

    # ── GSTR-1 DOCS fields ──
    document_type           = Column(String, nullable=True)
    document_nature         = Column(String, nullable=True)
    document_series         = Column(String, nullable=True)

    # Soft cancellation — NEVER hard-delete, set this flag instead.
    is_cancelled = Column(Boolean, nullable=False, default=False)
    cancelled_at = Column(DateTime, nullable=True)

    # Cascade deletes — deleting an invoice removes its lines.
    items = relationship(
        "GstSalesInvoiceItem",
        back_populates="invoice",
        cascade="all, delete-orphan",
    )


class GstSalesInvoiceItem(Base):
    __tablename__ = "gst_sales_invoice_items"

    id = Column(Integer, primary_key=True, index=True)

    gst_invoice_id = Column(
        Integer,
        ForeignKey("gst_sales_invoice.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    product_id = Column(Integer, nullable=False, index=True)
    product_name = Column(String, nullable=False)
    variant_name = Column(String, nullable=True)
    hsn_code = Column(String, nullable=False, default="")

    quantity = Column(Float, nullable=False)
    selling_price = Column(Float, nullable=False)
    taxable_amount = Column(Float, nullable=False)

    sales_cgst_percentage = Column(Float, nullable=False, default=0.0)
    sales_sgst_percentage = Column(Float, nullable=False, default=0.0)
    sales_igst_percentage = Column(Float, nullable=False, default=0.0)

    cgst_amount = Column(Float, nullable=False, default=0.0)
    sgst_amount = Column(Float, nullable=False, default=0.0)
    igst_amount = Column(Float, nullable=False, default=0.0)

    net_value = Column(Float, nullable=False, default=0.0)

    # ── GSTR-1 item-level fields (v23) ──
    cess_rate   = Column(Float, nullable=False, default=0.0)
    cess_amount = Column(Float, nullable=False, default=0.0)
    uqc         = Column(String, nullable=True)          # GST Unit Quantity Code
    hsn_description = Column(String, nullable=True)       # product description for HSN summary
    supply_classification = Column(String, nullable=False, default="TAXABLE") # TAXABLE, NIL_RATED, EXEMPT, NON_GST

    invoice = relationship("GstSalesInvoice", back_populates="items")


# Composite indices that the report code is most likely to use —
# (shop, created_at) for "show me the last 30 days of invoices",
# (shop, customer_gst) for B2B customer drill-downs.
Index(
    "ix_gst_sales_invoice_shop_created",
    GstSalesInvoice.shop_id,
    GstSalesInvoice.created_at,
)
Index(
    "ix_gst_sales_invoice_shop_customer_gst",
    GstSalesInvoice.shop_id,
    GstSalesInvoice.customer_gst,
)
