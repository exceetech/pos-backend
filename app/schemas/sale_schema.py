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