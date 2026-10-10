"""Schemas for the Stage 3D allocation / pool / claim sync."""
from typing import List, Optional
from pydantic import BaseModel


class AllocationDto(BaseModel):
    local_id: int
    source_type: str
    source_id: int = 0
    bill_number: Optional[str] = None
    line_ordinal: Optional[int] = None
    product_id: int
    purchase_invoice_id: Optional[int] = None
    batch_local_id: Optional[int] = None
    quantity: float
    quantity_restored: float = 0.0
    unit_cost_net: float = 0.0
    unit_cost_gross: float = 0.0
    created_at: float = 0.0


class PoolDto(BaseModel):
    local_id: int
    note_local_id: int
    purchase_invoice_id: int
    product_id: int
    gone_qty: float
    delta_gross: float
    note_date: float


class ClaimDto(BaseModel):
    local_id: int
    allocation_local_id: int
    pool_local_id: int
    note_local_id: int
    product_id: Optional[int] = None
    qty: float
    amount: float
    claim_date: float
    source_type: str
    source_id: int = 0
    bill_number: Optional[str] = None


class AllocationSyncRequest(BaseModel):
    origin: str = ""
    allocations: List[AllocationDto] = []
    pools: List[PoolDto] = []
    claims: List[ClaimDto] = []


class AllocationSyncResponse(BaseModel):
    allocation_ids: List[int] = []   # accepted local ids
    pool_ids: List[int] = []
    claim_ids: List[int] = []
    message: Optional[str] = None
