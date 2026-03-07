from pydantic import BaseModel
from typing import List

class BillItemRequest(BaseModel):
    shop_product_id: int
    quantity: int


class CreateBillRequest(BaseModel):
    bill_number: str
    items: List[BillItemRequest]
    payment_method: str
    gst: float
    discount: float
    total_amount: float