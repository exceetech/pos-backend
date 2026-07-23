from sqlalchemy import Column, Integer, Float, Boolean, ForeignKey, String, UniqueConstraint
from app.database import Base

class ShopProduct(Base):
    __tablename__ = "shop_products"
    __table_args__ = (
        UniqueConstraint('shop_id', 'global_product_id', 'variant_name', name='uix_shop_global_variant'),
    )

    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False)
    global_product_id = Column(Integer, ForeignKey("global_products.id"), nullable=False)

    variant_name = Column(String, nullable=True)
    unit = Column(String, default="unit")

    price = Column(Float, nullable=False)
    is_active = Column(Boolean, default=True)
    is_purchased = Column(Boolean, default=False)
    is_tax_inclusive = Column(Boolean, default=False)

    # GST fields
    hsn_code = Column(String, nullable=True)
    default_gst_rate = Column(Float, default=0.0)

    # Intra-state split (CGST + SGST) and inter-state (IGST).
    cgst_percentage = Column(Float, default=0.0, nullable=False)
    sgst_percentage = Column(Float, default=0.0, nullable=False)
    igst_percentage = Column(Float, default=0.0, nullable=False)

    # ── GSTR-1 product master fields (v23) ──
    official_uqc     = Column(String, nullable=True)   # explicit GST UQC override
    hsn_description  = Column(String, nullable=True)   # description for HSN summary
    cess_rate        = Column(Float, default=0.0, nullable=False)
    supply_classification = Column(String, nullable=False, default="TAXABLE") # TAXABLE, NIL_RATED, EXEMPT, NON_GST

    # ── Category (v40) ── plain string; predefined vocabulary lives on
    # the client, custom values are also stored in `shop_categories`.
    category = Column(String, nullable=True, default="")