from pydantic import BaseModel, Field
from typing import List

class BillItemRequest(BaseModel):
    shop_product_id: int
    quantity: float
    variant: str | None = None


class CreateBillRequest(BaseModel):
    items: List[BillItemRequest]
    payment_method: str
    discount: float = 0.0