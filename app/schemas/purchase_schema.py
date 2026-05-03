# schemas/purchase_schema.py

from pydantic import BaseModel
from typing import List, Optional


class PurchaseItemDto(BaseModel):
    local_id: int
    shop_product_id: Optional[int]

    product_name: str
    variant: Optional[str]
    hsn_code: Optional[str]

    quantity: float
    unit: Optional[str]

    taxable_amount: float
    invoice_value: float
    cost_price: float

    purchase_cgst_percentage: float = 0.0
    purchase_sgst_percentage: float = 0.0
    purchase_igst_percentage: float = 0.0

    purchase_cgst_amount: float = 0.0
    purchase_sgst_amount: float = 0.0
    purchase_igst_amount: float = 0.0

    sales_cgst_percentage: float = 0.0
    sales_sgst_percentage: float = 0.0
    sales_igst_percentage: float = 0.0


class PurchaseDto(BaseModel):
    local_id: int

    invoice_number: str
    supplier_gstin: Optional[str]
    supplier_name: str
    state: str

    taxable_amount: float
    cgst_percentage: float
    sgst_percentage: float
    igst_percentage: float

    cgst_amount: float
    sgst_amount: float
    igst_amount: float

    invoice_value: float
    created_at: float

    items: List[PurchaseItemDto]


class PurchaseSyncRequest(BaseModel):
    purchases: List[PurchaseDto]


class PurchaseSyncResponse(BaseModel):
    success_count: int
    purchase_id_map: dict