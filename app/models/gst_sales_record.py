import uuid
from sqlalchemy import Boolean, Column, String, Float, DateTime, Integer, ForeignKey, BigInteger
from datetime import datetime
from app.database import Base


def _uuid():
    return str(uuid.uuid4())


class GstSalesRecord(Base):
    """
    One record per bill line-item with full GST breakdown.
    Used exclusively for GST report generation (GSTR-1, GSTR-3B, HSN Summary).
    Written atomically when a bill is created — never derived from raw bills/bill_items.
    """
    __tablename__ = "gst_sales_records"

    id = Column(String, primary_key=True, default=_uuid)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False, index=True)

    # Invoice identification
    invoice_number = Column(String, nullable=False, index=True)
    invoice_date = Column(DateTime, nullable=False, index=True)

    # Customer
    customer_type = Column(String, nullable=False)      # B2B / B2C
    customer_gstin = Column(String, nullable=True)       # only for B2B

    # Supply info
    place_of_supply = Column(String, nullable=False)     # 2-digit state code
    supply_type = Column(String, nullable=False)         # intrastate / interstate

    # Product
    hsn_code = Column(String, nullable=False)
    product_name = Column(String, nullable=False)
    quantity = Column(Float, nullable=False)
    unit = Column(String, default="piece")

    # Tax
    taxable_value = Column(Float, nullable=False)
    gst_rate = Column(Float, nullable=False)             # e.g. 18.0
    cgst_amount = Column(Float, default=0.0)
    sgst_amount = Column(Float, default=0.0)
    igst_amount = Column(Float, default=0.0)
    total_amount = Column(Float, nullable=False)

    # Sync
    sync_status = Column(String, default="pending")      # pending / synced / failed
    device_id = Column(String, default="")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ── GSTR-1 enrichment fields (v23) ──────────────────────────────

    # Customer detail fields (captured at invoice time).
    customer_name  = Column(String, nullable=True)
    business_name  = Column(String, nullable=True)
    customer_phone = Column(String, nullable=True)
    customer_state = Column(String, nullable=True)
    customer_state_code = Column(String, nullable=True)  # 2-digit GST state code

    # Invoice-level GSTR-1 fields.
    reverse_charge         = Column(String, nullable=False, default="N")
    gstr_invoice_type      = Column(String, nullable=False, default="Regular")
    ecommerce_gstin        = Column(String, nullable=True)
    ecommerce_operator_name = Column(String, nullable=True)

    # New ECO fields (Table 14/15)
    eco_nature_of_supply    = Column(String, nullable=True)
    eco_document_type       = Column(String, nullable=True)
    eco_supplier_gstin      = Column(String, nullable=True)
    eco_supplier_name       = Column(String, nullable=True)
    eco_recipient_gstin     = Column(String, nullable=True)
    eco_recipient_name      = Column(String, nullable=True)
    eco_role                = Column(String, nullable=True)

    # Item-level GSTR-1 product master fields.
    cess_rate       = Column(Float, nullable=False, default=0.0)
    cess_amount     = Column(Float, nullable=False, default=0.0)
    uqc             = Column(String, nullable=True)
    hsn_description = Column(String, nullable=True)

    # Soft cancellation flag.
    is_cancelled = Column(Boolean, nullable=False, default=False)
