"""Pydantic schemas for the user-event-log sync + admin endpoints."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class UserEventDto(BaseModel):
    event_type: str
    screen: Optional[str] = None
    detail: Optional[str] = None
    # Epoch millis from the device clock — matches the pattern used by
    # every other sync DTO in this app (e.g. PurchaseBatchDto.created_at).
    created_at: float = 0.0


class UserEventSyncRequest(BaseModel):
    events: List[UserEventDto]


class UserEventSyncResponse(BaseModel):
    success_count: int = 0
    message: Optional[str] = None


class UserEventOut(BaseModel):
    id: int
    shop_id: int
    event_type: str
    screen: Optional[str] = None
    detail: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class UserEventListResponse(BaseModel):
    events: List[UserEventOut]
    total: int


class UserEventDeleteResponse(BaseModel):
    deleted_count: int
    message: Optional[str] = None
