from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class ImportServiceBase(BaseModel):
    local_id: Optional[int] = None
    invoice_number: str
    invoice_date: int  # Epoch millis from Android
    invoice_value: float
    place_of_supply: str
    
    rate: float
    taxable_value: float
    igst_paid: float
    cess_paid: float
    
    eligibility_for_itc: str = "Inputs"
    availed_itc_igst: float = 0.0
    availed_itc_cess: float = 0.0

    sync_status: str = "synced"
    device_id: Optional[str] = None

class ImportServiceCreate(ImportServiceBase):
    pass

class ImportServiceResponse(ImportServiceBase):
    id: int
    shop_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
