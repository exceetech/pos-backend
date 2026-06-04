from pydantic import BaseModel
from typing import List, Optional, Dict

class PurchaseImportDetailsDto(BaseModel):
    local_id: int
    purchase_id: Optional[int] = None
    local_purchase_id: int
    port_code: str
    bill_of_entry_number: str
    bill_of_entry_date: float
    bill_of_entry_value: float
    document_type: str
    sez_supplier_gstin: Optional[str] = None
    sync_status: str
    device_id: str
    created_at: float
    updated_at: float

class PurchaseImportDetailsSyncRequest(BaseModel):
    records: List[PurchaseImportDetailsDto]

class PurchaseImportDetailsSyncResponse(BaseModel):
    success_count: int
    record_id_map: Dict[str, int]
    failed: List[str]
    message: str

class PurchaseImportDetailsOut(BaseModel):
    id: int
    shop_id: int
    purchase_id: Optional[int]
    local_id: Optional[int]
    local_purchase_id: Optional[int]
    port_code: str
    bill_of_entry_number: str
    bill_of_entry_date: float
    bill_of_entry_value: float
    document_type: str
    sez_supplier_gstin: Optional[str]
    sync_status: str
    device_id: Optional[str]
    created_at: float
    updated_at: float
    
    class Config:
        from_attributes = True
