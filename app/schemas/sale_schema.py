from pydantic import BaseModel
from typing import List, Optional

class SaleItemDto(BaseModel):
    product_id: int
    quantity: float
    selling_price: float
    cost_price: float
    product_name: str
    variant: Optional[str] = None


class CreateSaleRequest(BaseModel):
    items: List[SaleItemDto]
    bill_number: Optional[str] = None
    # Idempotency key (Report 5 fix): same local bill + device combo the
    # app already uses for /bills/create. Lets a retried/backfilled call
    # be recognized as "already delivered" instead of duplicating rows.
    client_bill_id: Optional[int] = None
    client_device_id: Optional[str] = None