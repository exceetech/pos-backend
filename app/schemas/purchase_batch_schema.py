"""Pydantic schemas for the hybrid-inventory purchase_batches sync."""

from typing import List, Optional
from pydantic import BaseModel


class PurchaseBatchDto(BaseModel):
    local_id: int
    product_id: int
    purchase_invoice_id: Optional[int] = None

    supplier_name: Optional[str] = None
    supplier_gstin: Optional[str] = None
    invoice_number: Optional[str] = None
    batch_code: Optional[str] = None

    quantity_purchased: float
    quantity_remaining: float
    unit_cost_excluding_tax: float

    gst_percent: float = 0.0
    cgst_percent: float = 0.0
    sgst_percent: float = 0.0
    igst_percent: float = 0.0

    invoice_value: float = 0.0
    taxable_value: float = 0.0

    invoice_date: Optional[float] = None
    created_at: float = 0.0


class PurchaseBatchSyncRequest(BaseModel):
    batches: List[PurchaseBatchDto]


class PurchaseBatchSyncResponse(BaseModel):
    success_count: int = 0
    batch_id_map: dict = {}
    message: Optional[str] = None
