# schemas/purchase_schema.py

from pydantic import BaseModel
from typing import List, Optional


class PurchaseItemDto(BaseModel):
    local_id: int
    shop_product_id: Optional[int] = None

    product_name: str
    variant: Optional[str] = None
    hsn_code: Optional[str] = None

    quantity: float
    unit: Optional[str] = None

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
    message: Optional[str] = None