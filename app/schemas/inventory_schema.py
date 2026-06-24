from typing import Optional, Union
from pydantic import BaseModel
from datetime import datetime

class InventoryLogRequest(BaseModel):
    product_id: int
    type: str
    quantity: float
    price: float
    date: Optional[Union[float, int]] = None
    # Stable client idempotency key ("<device_id>:<local_log_id>"); optional so
    # older clients still work (they fall back to content-based dedupe).
    client_uid: Optional[str] = None