from sqlalchemy import (
    Column, Integer, String, Boolean, Float, ForeignKey, UniqueConstraint
)
from app.database import Base


class GlobalProductVariant(Base):
    __tablename__ = "global_product_variants"

    __table_args__ = (
        UniqueConstraint(
            "product_id", "variant_name", name="uix_gpv_product_variant"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    product_id = Column(Integer, ForeignKey("global_products.id"), nullable=False)

    variant_name = Column(String, nullable=False)
    unit = Column(String, default="unit")

    is_verified = Column(Boolean, default=False)

    # ── Autofill / provenance fields (v-autofill) ──────────────────
    # created_by_shop_id lets a shop see its own still-unverified
    # submissions (verified-OR-mine filter) without exposing them to
    # other shops. The statutory tax fields are national facts and are
    # safe to share once verified. NOTE: price is intentionally NOT
    # stored here — it is per-shop and must never be cross-filled.
    created_by_shop_id = Column(Integer, ForeignKey("shops.id"), nullable=True)

    hsn_code = Column(String, nullable=True)
    hsn_description = Column(String, nullable=True)
    official_uqc = Column(String, nullable=True)
    default_gst_rate = Column(Float, default=0.0)
    cgst_percentage = Column(Float, default=0.0)
    sgst_percentage = Column(Float, default=0.0)
    igst_percentage = Column(Float, default=0.0)
    cess_rate = Column(Float, default=0.0)
