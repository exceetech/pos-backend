from pydantic import BaseModel
from typing import List

class BillItemRequest(BaseModel):
    shop_product_id: int
    quantity: int


class CreateBillRequest(BaseModel):
    items: List[BillItemRequest]
    payment_method: str
    discount: float