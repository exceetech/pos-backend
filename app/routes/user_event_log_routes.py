"""
Per-shop breadcrumb/event log — support tooling, not analytics.

  • POST   /events/sync              — shop-scoped batch upload from the app
  • GET    /admin/events             — support lookup: a shop's recent events
  • DELETE /admin/events             — admin cleanup: by shop_id, by id list,
                                        or everything older than N days

Retention: rows are also auto-deleted after 90 days by a daily scheduled
job (app/services/event_log_cleanup_service.py) — the DELETE endpoint here
is for on-demand admin cleanup on top of that, not a replacement for it.
"""
import logging
from datetime import timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_shop, require_admin
from app.models.user_event_log import UserEventLog
from app.util.time_utils import epoch_ms_to_utc, utc_now
from app.schemas.user_event_log_schema import (
    UserEventSyncRequest,
    UserEventSyncResponse,
    UserEventListResponse,
    UserEventDeleteResponse,
)

router = APIRouter(tags=["User Event Log"])
logger = logging.getLogger(__name__)


@router.post("/events/sync", response_model=UserEventSyncResponse)
def sync_user_events(
    payload: UserEventSyncRequest,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop),
):
    """
    Append-only — these are breadcrumbs, not synced/updated records, so
    there's no idempotency key or upsert-by-local_id logic here (unlike
    every other sync endpoint in this app). A retried batch just inserts
    the same events again, which is harmless for a debugging trail and
    far simpler than tracking per-event dedupe keys for something this
    low-stakes.
    """
    rows = [
        UserEventLog(
            shop_id=current_shop.id,
            event_type=e.event_type,
            screen=e.screen,
            detail=e.detail,
            created_at=epoch_ms_to_utc(int(e.created_at)) if e.created_at else utc_now(),
        )
        for e in payload.events
    ]
    if rows:
        db.bulk_save_objects(rows)
        db.commit()

    return UserEventSyncResponse(
        success_count=len(rows),
        message=f"{len(rows)} event(s) recorded",
    )


@router.get("/admin/events", response_model=UserEventListResponse, dependencies=[Depends(require_admin)])
def list_user_events(
    shop_id: int = Query(..., description="Shop to pull the event trail for"),
    days: int = Query(7, ge=1, le=90, description="How many days back to look"),
    limit: int = Query(500, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    """
    The actual support-investigation query: "what did this shop do in the
    last N days?" Ordered oldest-first so it reads like a timeline.
    """
    since = utc_now() - timedelta(days=days)
    q = (
        db.query(UserEventLog)
        .filter(UserEventLog.shop_id == shop_id, UserEventLog.created_at >= since)
        .order_by(UserEventLog.created_at.asc())
        .limit(limit)
    )
    events = q.all()
    return UserEventListResponse(events=events, total=len(events))


@router.delete("/admin/events", response_model=UserEventDeleteResponse, dependencies=[Depends(require_admin)])
def delete_user_events(
    shop_id: Optional[int] = Query(None, description="Delete all events for this shop"),
    event_ids: Optional[List[int]] = Query(None, description="Delete these specific event ids"),
    older_than_days: Optional[int] = Query(None, ge=1, description="Delete everything older than N days"),
    db: Session = Depends(get_db),
):
    """
    On-demand admin cleanup, on top of the automatic 90-day job. Exactly
    one of shop_id / event_ids / older_than_days must be given — this is
    a destructive bulk-delete endpoint, so it deliberately doesn't support
    "delete everything" with no filter at all.
    """
    filters_given = sum(x is not None for x in (shop_id, event_ids, older_than_days))
    if filters_given != 1:
        return UserEventDeleteResponse(
            deleted_count=0,
            message="Provide exactly one of shop_id, event_ids, or older_than_days.",
        )

    q = db.query(UserEventLog)
    if shop_id is not None:
        q = q.filter(UserEventLog.shop_id == shop_id)
    elif event_ids is not None:
        q = q.filter(UserEventLog.id.in_(event_ids))
    else:
        cutoff = utc_now() - timedelta(days=older_than_days)
        q = q.filter(UserEventLog.created_at < cutoff)

    deleted_count = q.delete(synchronize_session=False)
    db.commit()

    logger.info("Admin deleted %d user_event_log row(s)", deleted_count)
    return UserEventDeleteResponse(
        deleted_count=deleted_count,
        message=f"Deleted {deleted_count} event(s)",
    )
