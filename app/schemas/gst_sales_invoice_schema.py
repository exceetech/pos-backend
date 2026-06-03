"""
Pydantic schemas for the GST-aware sales invoice batch sync.

Field names match the Android Retrofit DTOs in
`Easy_Billing/app/src/main/java/com/example/easy_billing/network/GstSalesInvoiceModels.kt`
1:1. Keep them in lock-step or the offline replay path will fail
to deserialize on the server side.
"""
from datetime import datetime
from typing import List, Optional, Dict

from pydantic import BaseModel, Field


# --------------------------------------------------------------------
#  Request DTOs (POST /gst-sales/sync)
# --------------------------------------------------------------------

class CreateGstSalesItem(BaseModel):
    product_id: int
    product_name: str
    variant_name: Optional[str] = None
    hsn_code: str = ""

    quantity: float
    selling_price: float
    taxable_amount: float

    sales_cgst_percentage: float = 0.0
    sales_sgst_percentage: float = 0.0
    sales_igst_percentage: float = 0.0

    cgst_amount: float = 0.0
    sgst_amount: float = 0.0
    igst_amount: float = 0.0

    net_value: float = 0.0

    # ── GSTR-1 item-level fields (v23) ──
    cess_rate: float = 0.0
    cess_amount: float = 0.0
    uqc: Optional[str] = None
    hsn_description: Optional[str] = None
    supply_classification: str = "TAXABLE"


class CreateGstSalesInvoice(BaseModel):
    local_id: int
    bill_id: Optional[int] = None

    invoice_type: str = Field(..., description="B2B or B2C")
    gst_scheme: str = ""

    customer_name: Optional[str] = None
    business_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_gst: Optional[str] = None
    customer_state: Optional[str] = None

    subtotal: float = 0.0
    total_cgst: float = 0.0
    total_sgst: float = 0.0
    total_igst: float = 0.0
    total_tax: float = 0.0
    grand_total: float = 0.0

    # epoch millis — converted to a UTC datetime on insert
    created_at: int = 0

    # ── GSTR-1 invoice-level fields (v23) ──
    invoice_number: str = ""
    invoice_date: int = 0          # epoch millis
    reverse_charge: str = "N"
    gstr_invoice_type: str = "Regular"
    customer_state_code: Optional[str] = None
    ecommerce_gstin: Optional[str] = None
    ecommerce_operator_name: Optional[str] = None

    # New ECO fields (Table 14/15)
    eco_nature_of_supply: Optional[str] = None
    eco_document_type: Optional[str] = None
    eco_supplier_gstin: Optional[str] = None
    eco_supplier_name: Optional[str] = None
    eco_recipient_gstin: Optional[str] = None
    eco_recipient_name: Optional[str] = None
    eco_role: Optional[str] = None

    # ── GSTR-1 DOCS fields ──
    document_type: Optional[str] = None
    document_nature: Optional[str] = None
    document_series: Optional[str] = None

    is_cancelled: bool = False
    cancelled_at: Optional[int] = None  # epoch millis

    items: List[CreateGstSalesItem] = []


class GstSalesSyncBatchRequest(BaseModel):
    invoices: List[CreateGstSalesInvoice]


class GstSalesSyncBatchResponse(BaseModel):
    success_count: int = 0
    failed_count: int = 0
    invoice_id_map: Dict[str, int] = {}
    message: Optional[str] = None


# --------------------------------------------------------------------
#  Response DTOs (GET /gst-sales/{shop_id})
# --------------------------------------------------------------------

class GstSalesInvoiceItemOut(BaseModel):
    id: int
    product_id: int
    product_name: str
    variant_name: Optional[str] = None
    hsn_code: str = ""

    quantity: float
    selling_price: float
    taxable_amount: float

    sales_cgst_percentage: float = 0.0
    sales_sgst_percentage: float = 0.0
    sales_igst_percentage: float = 0.0

    cgst_amount: float = 0.0
    sgst_amount: float = 0.0
    igst_amount: float = 0.0
    net_value: float = 0.0

    # ── GSTR-1 item-level fields (v23) ──
    cess_rate: float = 0.0
    cess_amount: float = 0.0
    uqc: Optional[str] = None
    hsn_description: Optional[str] = None
    supply_classification: str = "TAXABLE"

    class Config:
        from_attributes = True


class GstSalesInvoiceOut(BaseModel):
    id: int
    shop_id: int
    bill_id: Optional[int] = None

    invoice_type: str
    gst_scheme: str

    customer_name: Optional[str] = None
    business_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_gst: Optional[str] = None
    customer_state: Optional[str] = None

    subtotal: float
    total_cgst: float
    total_sgst: float
    total_igst: float
    total_tax: float
    grand_total: float

    created_at: Optional[datetime] = None

    # ── GSTR-1 invoice-level fields (v23) ──
    invoice_number: str = ""
    invoice_date: Optional[int] = None
    reverse_charge: str = "N"
    gstr_invoice_type: str = "Regular"
    customer_state_code: Optional[str] = None
    ecommerce_gstin: Optional[str] = None
    ecommerce_operator_name: Optional[str] = None

    # New ECO fields (Table 14/15)
    eco_nature_of_supply: Optional[str] = None
    eco_document_type: Optional[str] = None
    eco_supplier_gstin: Optional[str] = None
    eco_supplier_name: Optional[str] = None
    eco_recipient_gstin: Optional[str] = None
    eco_recipient_name: Optional[str] = None
    eco_role: Optional[str] = None

    document_type: Optional[str] = None
    document_nature: Optional[str] = None
    document_series: Optional[str] = None

    is_cancelled: bool = False
    cancelled_at: Optional[datetime] = None

    items: List[GstSalesInvoiceItemOut] = []

    class Config:
        from_attributes = True


# --------------------------------------------------------------------
#  Single-invoice create body (POST /gst-sales)
# --------------------------------------------------------------------
# Used by clients that want to push one invoice at a time instead
# of batching. Identical body shape to the batch element.

class GstSalesInvoiceCreate(CreateGstSalesInvoice):
    pass


# --------------------------------------------------------------------
#  Cancel / Void  (POST /gst-sales/cancel)
# --------------------------------------------------------------------

class GstSalesCancelRequest(BaseModel):
    """
    Sent by the mobile client after the user voids an invoice.
    Either `invoice_number` or `server_id` is required to locate the row.
    """
    invoice_number: Optional[str] = None
    server_id: Optional[int] = None
    cancelled_at: Optional[int] = None   # epoch millis; server uses now() if omitted


class GstSalesCancelResponse(BaseModel):
    success: bool = True
    server_id: Optional[int] = None
    message: Optional[str] = None
