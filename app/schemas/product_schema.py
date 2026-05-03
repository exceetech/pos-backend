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

    # GST fields (mandatory when GST is enabled)
    hsn_code: Optional[str] = None
    default_gst_rate: Optional[float] = 0.0

class ProductResponse(BaseModel):
    id: int
    name: str
    price: float

    class Config:
        from_attributes = True