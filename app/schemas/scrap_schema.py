# schemas/scrap_schema.py
"""Pydantic schemas for the scrap endpoints — mirrors the
   purchase-return shapes with a `quantity` field instead of
   `quantity_returned` and an extra `reason` field."""

from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Dict
from datetime import datetime


class ScrapDto(BaseModel):
    local_id: int
    shop_id: str
    shop_product_id: Optional[int] = None

    product_name: str
    variant_name: Optional[str] = None
    hsn_code: Optional[str] = None

    quantity: float
    taxable_amount: float = 0.0
    invoice_value: float = 0.0

    cgst_percentage: float = 0.0
    sgst_percentage: float = 0.0
    igst_percentage: float = 0.0

    cgst_amount: float = 0.0
    sgst_amount: float = 0.0
    igst_amount: float = 0.0

    state: str = ""
    reason: str = "Scrap"

    created_at: int


class ScrapCreateRequest(ScrapDto):
    pass


class ScrapSyncRequest(BaseModel):
    records: List[ScrapDto]


class ScrapOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    shop_id: int
    shop_product_id: Optional[int] = None

    product_name: str
    variant_name: Optional[str] = None
    hsn_code: Optional[str] = None

    quantity: float
    taxable_amount: float
    invoice_value: float

    cgst_percentage: float
    sgst_percentage: float
    igst_percentage: float

    cgst_amount: float
    sgst_amount: float
    igst_amount: float

    state: str
    reason: str

    created_at: datetime


class ScrapSyncResponse(BaseModel):
    success_count: int = 0
    record_id_map: Dict[str, int] = {}
    failed: List[Dict] = []
    message: Optional[str] = None
