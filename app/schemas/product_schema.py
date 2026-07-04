from pydantic import BaseModel
from typing import Optional, List

class AddProductRequest(BaseModel):
    name: str
    variant_name: Optional[str] = None
    unit: str
    price: float

    track_inventory: bool = False
    is_purchased: bool = False
    is_tax_inclusive: bool = False
    initial_stock: Optional[float] = 0
    cost_price: Optional[float] = 0

    # GST fields (mandatory when GST is enabled)
    hsn_code: Optional[str] = None
    default_gst_rate: Optional[float] = 0.0

    # Sales tax percentages stored on the product master
    cgst_percentage: Optional[float] = 0.0
    sgst_percentage: Optional[float] = 0.0
    igst_percentage: Optional[float] = 0.0

    # ── GSTR-1 product master fields (v23) ──
    official_uqc: Optional[str] = None
    hsn_description: Optional[str] = None
    cess_rate: float = 0.0
    supply_classification: str = "TAXABLE"
    category: str = ""

class ProductResponse(BaseModel):
    id: int
    name: str
    price: float
    is_tax_inclusive: bool = False

    class Config:
        from_attributes = True

class HsnVerificationResponse(BaseModel):
    valid: bool
    hsn: str
    description: Optional[str] = None
    message: Optional[str] = None

class VariantListResponse(BaseModel):
    product_name: str
    variants: list[str] = []

class ProductNameVerifyResponse(BaseModel):
    valid: bool
    name: str
    matched_global_id: Optional[int] = None
    message: Optional[str] = None

class UnitListResponse(BaseModel):
    units: list[str] = []


# ── Batch sync (POST /products/sync) ──────────────────────────────────────────

class ShopProductDto(BaseModel):
    """Single product entry in a batch-sync payload from the Android client."""
    local_id: int
    name: str
    variant: Optional[str] = None
    unit: str = "piece"
    price: float
    track_inventory: bool = False
    is_purchased: bool = False
    is_tax_inclusive: bool = False
    is_custom: bool = False
    is_active: bool = True
    hsn_code: Optional[str] = None
    cgst_percentage: float = 0.0
    sgst_percentage: float = 0.0
    igst_percentage: float = 0.0
    default_gst_rate: float = 0.0
    # ── GSTR-1 product master fields (v23) ──
    official_uqc: Optional[str] = None
    hsn_description: Optional[str] = None
    cess_rate: float = 0.0
    supply_classification: str = "TAXABLE"
    category: str = ""

class ShopProductSyncRequest(BaseModel):
    products: List[ShopProductDto]

class ShopProductSyncResponse(BaseModel):
    success_count: int = 0
    product_id_map: dict = {}
    message: Optional[str] = None


# ── Global product registration (POST /products/global/register) ──────────────

class GlobalProductRegisterRequest(BaseModel):
    name: str
    variant: Optional[str] = None
    unit: Optional[str] = None
    hsn_code: Optional[str] = None
    hsn_description: Optional[str] = None
    official_uqc: Optional[str] = None
    # Statutory autofill fields (shared once verified). Default None (not
    # 0.0) so an omitted field is distinguishable from an explicit 0 — this
    # lets a shop correct a rate down to 0 (NIL) in the refine branch.
    default_gst_rate: Optional[float] = None
    cgst_percentage: Optional[float] = None
    sgst_percentage: Optional[float] = None
    igst_percentage: Optional[float] = None
    cess_rate: Optional[float] = None

class GlobalProductRegisterResponse(BaseModel):
    success: bool = True
    global_id: Optional[int] = None
    name: str
    variant: Optional[str] = None
    hsn_code: Optional[str] = None
    message: Optional[str] = None