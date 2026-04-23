from pydantic import BaseModel
from typing import Optional

class AddProductRequest(BaseModel):
    name: str
    variant_name: Optional[str] = None
    unit: str
    price: float

    track_inventory: bool = False
    initial_stock: Optional[float] = 0
    cost_price: Optional[float] = 0

class ProductResponse(BaseModel):
    id: int
    name: str
    price: float

    class Config:
        from_attributes = True