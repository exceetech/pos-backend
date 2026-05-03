from typing import Optional
from pydantic import BaseModel
from datetime import datetime

class InventoryLogRequest(BaseModel):
    product_id: int
    type: str
    quantity: float
    price: float
    date: Optional[datetime] = None