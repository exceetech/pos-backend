from typing import Optional
from pydantic import BaseModel


class VariantResponse(BaseModel):
    id: int
    product_id: int
    variant_name: str
    unit: str

    # Statutory autofill fields (safe to share). Price is intentionally
    # never returned — it is per-shop.
    hsn_code: Optional[str] = None
    hsn_description: Optional[str] = None
    official_uqc: Optional[str] = None
    default_gst_rate: float = 0.0
    cgst_percentage: float = 0.0
    sgst_percentage: float = 0.0
    igst_percentage: float = 0.0
    cess_rate: float = 0.0

    class Config:
        from_attributes = True


class HsnResponse(BaseModel):
    hsn_code: str

    class Config:
        from_attributes = True
