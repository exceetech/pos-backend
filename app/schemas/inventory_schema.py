from typing import Optional, Union
from pydantic import BaseModel
from datetime import datetime

class InventoryLogRequest(BaseModel):
    product_id: int
    type: str
    quantity: float
    price: float
    date: Optional[Union[float, int]] = None