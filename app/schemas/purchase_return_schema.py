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

    # ── Debit/Credit Note fields (v25+) ──────────────────────────────────
    # All optional so old clients that haven't updated continue to work.
    note_number:             Optional[str] = None
    note_date:               Optional[int] = None   # epoch millis
    note_type:               Optional[str] = None   # "D" or "C"
    original_invoice_id:     Optional[int] = None
    original_invoice_number: Optional[str] = None
    original_invoice_date:   Optional[int] = None   # epoch millis
    place_of_supply:         Optional[str] = None
    supply_type:             Optional[str] = "intrastate"
    cess_amount:             float = 0.0
    tax_amount:              float = 0.0
    total_amount:            float = 0.0
    document_type:           Optional[str] = None
    document_nature:         Optional[str] = None
    document_series:         Optional[str] = None

    pre_gst: str = "N"
    reason_for_issuing_document: str = "Purchase return"
    note_refund_voucher_value: float = 0.0
    rate: float = 0.0
    eligibility_for_itc: str = "Inputs"
    availed_itc_integrated_tax: float = 0.0
    availed_itc_central_tax: float = 0.0
    availed_itc_state_tax: float = 0.0
    availed_itc_cess: float = 0.0
    invoice_type: str = "Regular"
    place_of_supply_code: str = ""


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

    # ── Debit/Credit Note fields (v25+) ──────────────────────────────────
    note_number:             Optional[str]  = None
    note_date:               Optional[int]  = None
    note_type:               Optional[str]  = None
    original_invoice_id:     Optional[int]  = None
    original_invoice_number: Optional[str]  = None
    original_invoice_date:   Optional[int]  = None
    place_of_supply:         Optional[str]  = None
    supply_type:             Optional[str]  = None
    cess_amount:             Optional[float] = None
    tax_amount:              Optional[float] = None
    total_amount:            Optional[float] = None
    document_type:           Optional[str]  = None
    document_nature:         Optional[str]  = None
    document_series:         Optional[str]  = None

    pre_gst:                 Optional[str]  = None
    reason_for_issuing_document: Optional[str] = None
    note_refund_voucher_value: Optional[float] = None
    rate:                    Optional[float] = None
    eligibility_for_itc:     Optional[str]  = None
    availed_itc_integrated_tax: Optional[float] = None
    availed_itc_central_tax:  Optional[float] = None
    availed_itc_state_tax:    Optional[float] = None
    availed_itc_cess:         Optional[float] = None
    invoice_type:            Optional[str]  = None
    place_of_supply_code:    Optional[str]  = None


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
