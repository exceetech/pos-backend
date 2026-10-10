"""Schemas for the Money Book sync."""
from typing import List, Optional
from pydantic import BaseModel


class MoneyEntryDto(BaseModel):
    uid: str
    local_id: int = 0
    direction: str
    mode: str
    amount: float
    reason: str
    source_type: str
    source_id: int = 0
    parent_type: str
    parent_id: int = 0
    party_name: str = ""
    ref_text: str = ""
    status: str = "RECEIVED"
    created_at: float = 0.0


class MoneyEntrySyncRequest(BaseModel):
    origin: str = ""
    entries: List[MoneyEntryDto] = []


class MoneyEntrySyncResponse(BaseModel):
    uids: List[str] = []          # accepted (or permanently rejected) - the app stops retrying these
    message: Optional[str] = None
