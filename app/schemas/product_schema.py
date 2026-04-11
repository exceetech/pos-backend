from pydantic import BaseModel
from typing import Optional

class AddProductRequest(BaseModel):
    name: str
    variant_name: Optional[str] = None
    unit: Optional[str] = "unit"
    price: float

class ProductResponse(BaseModel):
    id: int
    name: str
    price: float

    class Config:
        from_attributes = True