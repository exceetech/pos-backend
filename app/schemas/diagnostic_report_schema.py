"""Pydantic schemas for the on-demand full diagnostic-report upload."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel

from app.schemas.user_event_log_schema import UserEventDto


class DiagnosticReportUploadRequest(BaseModel):
    # Reuses the same DTO shape as the regular event sync — a diagnostic
    # report is just "every row currently in the local table," not a
    # different event format.
    events: List[UserEventDto]


class DiagnosticReportUploadResponse(BaseModel):
    report_id: int
    event_count: int
    message: Optional[str] = None


class DiagnosticReportSummary(BaseModel):
    """Lightweight listing row — no event payload, just enough to pick one."""
    id: int
    shop_id: int
    event_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class DiagnosticReportListResponse(BaseModel):
    reports: List[DiagnosticReportSummary]
    total: int


class DiagnosticReportDetail(BaseModel):
    """The full report — same shape as the summary, plus the raw events."""
    id: int
    shop_id: int
    event_count: int
    created_at: datetime
    events: list

    class Config:
        from_attributes = True
