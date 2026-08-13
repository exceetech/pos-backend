"""
Daily cleanup for user_event_logs — deletes anything older than the
retention window (90 days). Wired into the same APScheduler instance as
the other periodic jobs in app/main.py (run_expiry_check,
run_order_reconciliation).

This is the automatic side of retention; app/routes/user_event_log_routes.py
DELETE /admin/events is the on-demand admin side of it.
"""
import logging
from datetime import timedelta

from sqlalchemy.orm import Session

from app.models.user_event_log import UserEventLog
from app.util.time_utils import utc_now

logger = logging.getLogger(__name__)

RETENTION_DAYS = 90


def cleanup_old_user_events(db: Session) -> int:
    cutoff = utc_now() - timedelta(days=RETENTION_DAYS)
    deleted_count = (
        db.query(UserEventLog)
        .filter(UserEventLog.created_at < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    if deleted_count:
        logger.info("Cleaned up %d user_event_log row(s) older than %d days", deleted_count, RETENTION_DAYS)
    return deleted_count
