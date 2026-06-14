from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class BillItemRequest(BaseModel):
    shop_product_id: int
    product_name: Optional[str] = None
    quantity: float
    variant: Optional[str] = None
    unit: Optional[str] = "unit"
    
    unit_price: float = 0.0
    line_subtotal: float = 0.0
    discount_amount: float = 0.0
    taxable_amount: float = 0.0
    
    gst_rate: float = 0.0
    cgst_rate: float = 0.0
    sgst_rate: float = 0.0
    igst_rate: float = 0.0
    
    cgst_amount: float = 0.0
    sgst_amount: float = 0.0
    igst_amount: float = 0.0
    cess_amount: float = 0.0
    
    total_amount: float = 0.0
    hsn_code: str = ""

class CreateBillRequest(BaseModel):
    # Backward compatible fields
    items: List[BillItemRequest]
    payment_method: str = "Cash"
    discount: float = 0.0
    total_amount: float = 0.0
    gst: float = 0.0
    
    # Financial summaries
    subtotal: float = 0.0
    discount_amount: float = 0.0
    taxable_amount: float = 0.0
    
    cgst_amount: float = 0.0
    sgst_amount: float = 0.0
    igst_amount: float = 0.0
    cess_amount: float = 0.0
    gst_amount: float = 0.0
    
    round_off: float = 0.0
    final_amount: float = 0.0
    
    # GST metadata
    gst_scheme: str = "Regular"
    supply_type: str = "intrastate"
    customer_state: Optional[str] = None
    customer_state_code: Optional[str] = None
    invoice_type: str = "B2C"
    is_gst_invoice: bool = False

    # Idempotency key: the app's local bill id + device id. Optional so
    # older app versions still work; when present, /bills/create returns
    # the existing row instead of inserting a duplicate.
    client_bill_id: Optional[int] = None
    client_device_id: Optional[str] = None

    created_at: Optional[datetime] = None

    # Cancellation (void) state — covers bills cancelled on the device
    # BEFORE their first sync. Epoch millis, like the GST invoice DTOs.
    is_cancelled: bool = False
    cancelled_at: Optional[int] = None


class CancelBillRequest(BaseModel):
    """Void an already-synced bill. Identified by bill_number or by the
    idempotency pair (client_device_id, client_bill_id)."""
    bill_number: Optional[str] = None
    client_bill_id: Optional[int] = None
    client_device_id: Optional[str] = None
    cancelled_at: Optional[int] = None  # epoch millis