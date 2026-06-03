# schemas/credit_note_schema.py
"""
Pydantic schemas for credit note (sales return) endpoints.

Endpoint contract matches the Android-side DTOs in
`com.example.easy_billing.network.CreditNoteModels`:

  • POST /credit-notes/sync  → CreditNoteSyncRequest / CreditNoteSyncResponse
  • GET  /credit-notes       → List[CreditNoteDto]

All field names are snake_case to match SQLAlchemy ORM attribute names.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict


# ── Item-level DTO ────────────────────────────────────────────────────────────

class CreditNoteItemDto(BaseModel):
    """A single returned line item within a credit note."""
    product_id:           Optional[int]   = None
    product_name:         str
    variant:              Optional[str]   = None
    hsn_code:             Optional[str]   = None
    unit:                 Optional[str]   = None

    quantity_sold:        float = 0.0
    quantity_returned:    float = 0.0

    rate:                 float = 0.0
    cost_price_used:      float = 0.0

    taxable_value:        float = 0.0
    gst_rate:             float = 0.0
    cgst_amount:          float = 0.0
    sgst_amount:          float = 0.0
    igst_amount:          float = 0.0
    cess_amount:          float = 0.0
    tax_amount:           float = 0.0
    total_amount:         float = 0.0

    original_bill_item_id: Optional[int] = None


# ── Header-level DTO (used inside sync request) ───────────────────────────────

class CreditNoteDto(BaseModel):
    """
    A single credit note pushed from the Android client.

    `local_id` echoes the Android-side `CreditNote.id` so the sync
    response can return a {local_id → server_id} map.
    """
    local_id: int

    note_number:            str
    note_date:              int               # epoch millis
    note_type:              str = "C"
    note_supply_type:       Optional[str] = "Regular"

    original_invoice_id:    Optional[int]    = None
    original_invoice_number: Optional[str]   = None
    original_invoice_date:  Optional[int]    = None  # epoch millis

    customer_name:          Optional[str]    = None
    customer_gstin:         Optional[str]    = None

    place_of_supply:        Optional[str]    = None
    reverse_charge:         str = "N"
    supply_type:            str = "intrastate"
    ur_type:                Optional[str]    = None
    document_type:          Optional[str]    = None
    document_nature:        Optional[str]    = None
    document_series:        Optional[str]    = None

    taxable_value:          float = 0.0
    cgst_amount:            float = 0.0
    sgst_amount:            float = 0.0
    igst_amount:            float = 0.0
    cess_amount:            float = 0.0
    tax_amount:             float = 0.0
    total_amount:           float = 0.0

    sync_status:            str = "pending"
    created_at:             int  # epoch millis
    updated_at:             Optional[int] = None  # epoch millis; optional for backward compat

    items: List[CreditNoteItemDto] = []


# ── Sync request / response ───────────────────────────────────────────────────

class CreditNoteSyncRequest(BaseModel):
    """Bulk push: a list of credit notes to sync to the backend.

    The Android client sends this as `credit_notes` (not `notes`) — the field
    name here must match what Retrofit serialises.
    """
    credit_notes: List[CreditNoteDto]


class CreditNoteSyncResponse(BaseModel):
    """
    Per-note outcome map so the Android client can mark only the rows
    the server accepted as `syncStatus = 'synced'`.

      • success_count  — number of notes accepted
      • note_id_map    — local_id (string) → server id
      • failed         — {local_id, reason} for rejected notes
      • message        — human-readable summary
    """
    success_count: int = 0
    note_id_map:   Dict[str, int] = {}
    failed:        List[Dict]     = []
    message:       Optional[str]  = None


# ── Output schema (GET response) ──────────────────────────────────────────────

class CreditNoteItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:                   int
    note_id:              int
    product_id:           Optional[int]
    product_name:         str
    variant:              Optional[str]
    hsn_code:             Optional[str]
    unit:                 Optional[str]
    quantity_sold:        float
    quantity_returned:    float
    rate:                 float
    cost_price_used:      float
    taxable_value:        float
    gst_rate:             float
    cgst_amount:          float
    sgst_amount:          float
    igst_amount:          float
    cess_amount:          float
    tax_amount:           float
    total_amount:         float
    original_bill_item_id: Optional[int]


class CreditNoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:                     int
    shop_id:                int
    local_id:               Optional[int]
    note_number:            str
    note_date:              int
    note_type:              str
    note_supply_type:       Optional[str]
    original_invoice_id:    Optional[int]
    original_invoice_number: Optional[str]
    original_invoice_date:  Optional[int]
    customer_name:          Optional[str]
    customer_gstin:         Optional[str]
    place_of_supply:        Optional[str]
    reverse_charge:         str
    supply_type:            str
    ur_type:                Optional[str]
    document_type:          Optional[str]
    document_nature:        Optional[str]
    document_series:        Optional[str]
    taxable_value:          float
    cgst_amount:            float
    sgst_amount:            float
    igst_amount:            float
    cess_amount:            float
    tax_amount:             float
    total_amount:           float
    sync_status:            str
    created_at:             datetime
    updated_at:             datetime
    items:                  List[CreditNoteItemOut] = []
