# schemas/purchase_schema.py

from pydantic import BaseModel
from typing import List, Optional


class CancelPurchaseRequest(BaseModel):
    """Void an already-synced purchase. Resolved by server id when known, else
    by invoice_number, else by (shop, client_purchase_id/local_id)."""
    invoice_number: Optional[str] = None
    client_purchase_id: Optional[int] = None
    server_purchase_id: Optional[int] = None
    client_device_id: Optional[str] = None
    cancelled_at: Optional[int] = None  # epoch millis


class PurchaseItemDto(BaseModel):
    local_id: int
    shop_product_id: Optional[int] = None

    product_name: str
    variant: Optional[str] = None
    hsn_code: Optional[str] = None

    quantity: float
    unit: Optional[str] = None

    taxable_amount: float
    discount_amount: float = 0.0
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

    cess_percentage: float = 0.0
    cess_amount: float = 0.0
    eligibility_for_itc: str = "Inputs"
    availed_itc_igst: float = 0.0
    availed_itc_cgst: float = 0.0
    availed_itc_sgst: float = 0.0
    availed_itc_cess: float = 0.0
    hsn_description: str = ""
    official_uqc: str = ""
    supply_classification: str = "TAXABLE"


class PurchaseDto(BaseModel):
    local_id: int
    # Stable per-install id (Issue 10). Combined with local_id this lets the
    # server tell apart two different devices that independently numbered a
    # purchase "5" for the same shop, instead of treating the second push as
    # an update to the first device's purchase and silently overwriting it.
    client_device_id: Optional[str] = None

    invoice_number: str
    supplier_gstin: Optional[str] = None
    supplier_name: str
    state: str = ""

    taxable_amount: float = 0.0
    cgst_percentage: float = 0.0
    sgst_percentage: float = 0.0
    igst_percentage: float = 0.0

    cgst_amount: float = 0.0
    sgst_amount: float = 0.0
    igst_amount: float = 0.0

    invoice_value: float = 0.0
    # Epoch milliseconds — UTC midnight of the supplier-invoice day.
    # Nullable for clients that haven't pushed a date yet.
    invoice_date: Optional[float] = None
    is_credit: bool = False
    credit_account_id: Optional[int] = None
    created_at: float

    place_of_supply_code: str = ""
    reverse_charge: str = "N"
    invoice_type: str = "Regular"
    supply_type: str = "intrastate"
    cess_paid: float = 0.0
    eligibility_for_itc: str = "Inputs"
    availed_itc_integrated_tax: float = 0.0
    availed_itc_central_tax: float = 0.0
    availed_itc_state_tax: float = 0.0
    availed_itc_cess: float = 0.0
    purchase_source: str = "DOMESTIC"

    items: List[PurchaseItemDto]


class PurchaseSyncRequest(BaseModel):
    purchases: List[PurchaseDto]


class PurchaseSyncResponse(BaseModel):
    success_count: int
    purchase_id_map: dict
    item_id_map: dict = {}
    # Per-row failures (Issue 9). A purchase that fails validation is
    # reported here and skipped — it no longer aborts the whole batch and
    # discards purchases that were already valid.
    failed: List[dict] = []
    message: Optional[str] = None