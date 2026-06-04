from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ============================================================
# GST Profile (Store Registration)
# ============================================================

class GstProfileUpsert(BaseModel):
    gstin: str
    legal_name: Optional[str] = ""
    trade_name: Optional[str] = ""
    gst_scheme: Optional[str] = ""
    registration_type: Optional[str] = ""
    state_code: Optional[str] = ""
    address: Optional[str] = ""
    sync_status: Optional[str] = "pending"
    device_id: Optional[str] = ""


class GstProfileResponse(BaseModel):
    gstin: str
    legal_name: str
    trade_name: str
    gst_scheme: str
    registration_type: str
    state_code: str
    address: str
    sync_status: str

    class Config:
        from_attributes = True


# ============================================================
# GST Sales Records
# ============================================================

class GstSalesRecordCreate(BaseModel):
    id: str                        # UUID generated on device
    invoice_number: str
    invoice_date: datetime
    customer_type: str             # B2B / B2C
    customer_gstin: Optional[str] = None
    place_of_supply: str           # 2-digit state code
    supply_type: str               # intrastate / interstate
    hsn_code: str
    product_name: str
    quantity: float
    unit: str = "piece"
    taxable_value: float
    gst_rate: float
    cgst_amount: float = 0.0
    sgst_amount: float = 0.0
    igst_amount: float = 0.0
    total_amount: float
    sync_status: Optional[str] = "pending"
    device_id: Optional[str] = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # ── GSTR-1 enrichment fields (v23) ──
    customer_name: Optional[str] = None
    business_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_state: Optional[str] = None
    customer_state_code: Optional[str] = None
    reverse_charge: str = "N"
    gstr_invoice_type: str = "Regular"
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

    cess_rate: float = 0.0
    cess_amount: float = 0.0
    uqc: Optional[str] = None
    hsn_description: Optional[str] = None
    is_cancelled: bool = False


class GstSalesSyncRequest(BaseModel):
    records: List[GstSalesRecordCreate]


# ============================================================
# GST Purchase Records
# ============================================================

class GstPurchaseRecordCreate(BaseModel):
    id: str                        # UUID generated on device
    supplier_gstin: Optional[str] = None
    invoice_number: str
    invoice_date: datetime
    expense_type: str              # STOCK / EXPENSE / SERVICE
    hsn_sac_code: str
    description: Optional[str] = ""
    taxable_value: float
    gst_rate: float
    cgst_amount: float = 0.0
    sgst_amount: float = 0.0
    igst_amount: float = 0.0
    total_amount: float
    sync_status: Optional[str] = "pending"
    device_id: Optional[str] = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class GstPurchaseSyncRequest(BaseModel):
    records: List[GstPurchaseRecordCreate]


# ============================================================
# HSN Summary (Report)
# ============================================================

class HsnSummaryItem(BaseModel):
    hsn_code: str
    description: str = ""
    uom: str = "NOS"               # Unit of Measurement (GST portal standard)
    total_quantity: float
    taxable_value: float
    cgst_amount: float
    sgst_amount: float
    igst_amount: float
    total_tax: float


# ============================================================
# GSTR-1 (Outward Supplies)
# ============================================================

class Gstr1B2BInvoice(BaseModel):
    customer_gstin: str
    invoice_number: str
    invoice_date: str
    invoice_value: float
    place_of_supply: str
    supply_type: str
    taxable_value: float
    gst_rate: float
    cgst: float
    sgst: float
    igst: float


class Gstr1B2CItem(BaseModel):
    place_of_supply: str
    supply_type: str
    gst_rate: float
    taxable_value: float
    cgst: float
    sgst: float
    igst: float


class Gstr1Response(BaseModel):
    period_start: str
    period_end: str
    b2b: List[Gstr1B2BInvoice]
    b2c: List[Gstr1B2CItem]
    hsn_summary: List[HsnSummaryItem]
    total_taxable_value: float
    total_cgst: float
    total_sgst: float
    total_igst: float


# ============================================================
# GSTR-2 (Inward Supplies / Purchases)
# ============================================================

class Gstr2B2bItem(BaseModel):
    supplier_gstin: str
    invoice_number: str
    invoice_date: str
    invoice_value: float
    place_of_supply: str
    reverse_charge: str
    invoice_type: str
    rate: float
    taxable_value: float
    igst: float
    cgst: float
    sgst: float
    cess: float
    itc_eligibility: str
    availed_itc_igst: float
    availed_itc_cgst: float
    availed_itc_sgst: float
    availed_itc_cess: float

class Gstr2B2burItem(BaseModel):
    supplier_name: str
    invoice_number: str
    invoice_date: str
    invoice_value: float
    place_of_supply: str
    supply_type: str
    rate: float
    taxable_value: float
    igst: float
    cgst: float
    sgst: float
    cess: float
    itc_eligibility: str
    availed_itc_igst: float
    availed_itc_cgst: float
    availed_itc_sgst: float
    availed_itc_cess: float

class Gstr2ImpsItem(BaseModel):
    invoice_number: str
    invoice_date: str
    invoice_value: float
    place_of_supply: str
    rate: float
    taxable_value: float
    igst: float
    cess: float
    itc_eligibility: str
    availed_itc_igst: float
    availed_itc_cess: float

class Gstr2ImpgItem(BaseModel):
    port_code: str
    bill_of_entry_number: str
    bill_of_entry_date: str
    bill_of_entry_value: float
    document_type: str
    sez_supplier_gstin: str
    rate: float
    taxable_value: float
    igst: float
    cess: float
    itc_eligibility: str
    availed_itc_igst: float
    availed_itc_cess: float

class Gstr2CdnrItem(BaseModel):
    supplier_gstin: str
    note_number: str
    note_date: str
    invoice_number: str
    invoice_date: str
    pre_gst: str
    document_type: str
    reason: str
    supply_type: str
    note_value: float
    rate: float
    taxable_value: float
    igst: float
    cgst: float
    sgst: float
    cess: float
    itc_eligibility: str
    availed_itc_igst: float
    availed_itc_cgst: float
    availed_itc_sgst: float
    availed_itc_cess: float

class Gstr2CdnurItem(BaseModel):
    note_number: str
    note_date: str
    invoice_number: str
    invoice_date: str
    pre_gst: str
    document_type: str
    reason: str
    supply_type: str
    invoice_type: str
    note_value: float
    rate: float
    taxable_value: float
    igst: float
    cgst: float
    sgst: float
    cess: float
    itc_eligibility: str
    availed_itc_igst: float
    availed_itc_cgst: float
    availed_itc_sgst: float
    availed_itc_cess: float

class Gstr2ExempItem(BaseModel):
    description: str
    composition: float
    nil_rated: float
    exempted: float
    non_gst: float

class Gstr2HsnsumItem(BaseModel):
    hsn: str
    description: str
    uqc: str
    total_quantity: float
    total_value: float
    taxable_value: float
    igst: float
    cgst: float
    sgst: float
    cess: float

class Gstr2Response(BaseModel):
    period_start: str
    period_end: str
    b2b: List[Gstr2B2bItem] = []
    b2bur: List[Gstr2B2burItem] = []
    imps: List[Gstr2ImpsItem] = []
    impg: List[Gstr2ImpgItem] = []
    cdnr: List[Gstr2CdnrItem] = []
    cdnur: List[Gstr2CdnurItem] = []
    exemp: List[Gstr2ExempItem] = []
    hsnsum: List[Gstr2HsnsumItem] = []
    total_taxable_value: float
    total_itc_cgst: float
    total_itc_sgst: float
    total_itc_igst: float



# ============================================================
# GSTR-3B (Tax Liability Summary)
# ============================================================

class Gstr3BSupplyDetail(BaseModel):
    total_taxable_value: float
    total_cgst: float
    total_sgst: float
    total_igst: float
    total_cess: float = 0.0


class Gstr3BResponse(BaseModel):
    period_start: str
    period_end: str
    outward_taxable_supplies: Gstr3BSupplyDetail       # 3.1(a) Normal rated
    outward_zero_rated: Gstr3BSupplyDetail             # 3.1(b)
    outward_nil_rated: Gstr3BSupplyDetail              # 3.1(c)
    inward_nil_exempt: Gstr3BSupplyDetail              # 3.1(d)
    itc_available: Gstr3BSupplyDetail                  # ITC from purchases
    net_tax_payable_cgst: float
    net_tax_payable_sgst: float
    net_tax_payable_igst: float
