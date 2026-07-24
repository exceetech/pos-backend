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
    # Avg-cost audit, Fix 2: the average cost the client already computed
    # for this event, using the app's single weighted-average formula.
    # Optional so older app builds that don't send it yet keep working —
    # the route falls back to its own formula only when this is absent.
    resulting_average_cost: Optional[float] = None