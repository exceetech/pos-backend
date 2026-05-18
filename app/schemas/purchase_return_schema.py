# schemas/purchase_return_schema.py
"""
Pydantic schemas for the purchase-return endpoints.

Three request shapes:
  • PurchaseReturnCreateRequest   — single insert, used by POST /purchase-return
  • PurchaseReturnSyncRequest     — bulk push, used by POST /purchase-returns/sync

One response shape (PurchaseReturnOut) used by both single insert and the
GET /purchase-return/{shop_id} list endpoint.

PurchaseReturnDto matches the field names the Android client emits in
`com.example.easy_billing.network.PurchaseReturnDto` so the JSON parses
without any field-name acrobatics.
"""

from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Dict
from datetime import datetime


class PurchaseReturnDto(BaseModel):
    """Per-row payload — also used inside bulk sync."""
    local_id: int
    shop_id: str  # GSTIN string from the client; resolved to numeric
                  # shop_id server-side via current_shop dependency.
    shop_product_id: Optional[int] = None

    product_name: str
    variant_name: Optional[str] = None
    hsn_code: Optional[str] = None

    quantity_returned: float
    taxable_amount: float = 0.0
    invoice_value: float = 0.0

    cgst_percentage: float = 0.0
    sgst_percentage: float = 0.0
    igst_percentage: float = 0.0

    cgst_amount: float = 0.0
    sgst_amount: float = 0.0
    igst_amount: float = 0.0

    state: str = ""

    supplier_gstin: Optional[str] = None
    supplier_name: Optional[str] = None

    is_credit: bool = False
    credit_account_id: Optional[int] = None

    created_at: int  # epoch millis from client


class PurchaseReturnCreateRequest(PurchaseReturnDto):
    """Single-row create — same fields as the DTO. Wrapped here so
       the route signature reads cleanly."""
    pass


class PurchaseReturnSyncRequest(BaseModel):
    records: List[PurchaseReturnDto]


class PurchaseReturnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    shop_id: int
    shop_product_id: Optional[int] = None

    product_name: str
    variant_name: Optional[str] = None
    hsn_code: Optional[str] = None

    quantity_returned: float
    taxable_amount: float
    invoice_value: float

    cgst_percentage: float
    sgst_percentage: float
    igst_percentage: float

    cgst_amount: float
    sgst_amount: float
    igst_amount: float

    state: str

    supplier_gstin: Optional[str] = None
    supplier_name: Optional[str] = None

    is_credit: bool
    credit_account_id: Optional[int]

    created_at: datetime


class PurchaseReturnSyncResponse(BaseModel):
    """
    Per-row outcome map so the client can mark only the rows the
    server actually accepted as synced.

      • success_count        — total rows accepted
      • record_id_map        — local_id (string) → server id
      • failed               — list of {local_id, reason} for the
                               rows the server rejected
    """
    success_count: int = 0
    record_id_map: Dict[str, int] = {}
    failed: List[Dict] = []
    message: Optional[str] = None
