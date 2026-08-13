"""
Daily cleanup for diagnostic_reports — deletes anything older than the
retention window (14 days). Much shorter than user_event_logs' 90 days
since a report is only useful while a specific investigation is active.
Wired into the same APScheduler instance as the other periodic jobs in
app/main.py.

This is the automatic side of retention;
app/routes/diagnostic_report_routes.py DELETE /admin/diagnostic-reports
is the on-demand admin side of it.
"""
import logging
from datetime import timedelta

from sqlalchemy.orm import Session

from app.models.diagnostic_report import DiagnosticReport
from app.util.time_utils import local_now

logger = logging.getLogger(__name__)

RETENTION_DAYS = 14


def cleanup_old_diagnostic_reports(db: Session) -> int:
    # created_at is now stored in local (APP_TZ) wall-clock time — compare
    # against local_now(), not utc_now(), or the cutoff drifts by the
    # server's UTC offset and reports get kept ~5.5h longer/shorter than
    # the stated 14 days for IST shops.
    cutoff = local_now() - timedelta(days=RETENTION_DAYS)
    deleted_count = (
        db.query(DiagnosticReport)
        .filter(DiagnosticReport.created_at < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    if deleted_count:
        logger.info(
            "Cleaned up %d diagnostic_report row(s) older than %d days",
            deleted_count, RETENTION_DAYS,
        )
    return deleted_count
