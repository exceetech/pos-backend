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
