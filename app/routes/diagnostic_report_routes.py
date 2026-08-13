"""
On-demand full diagnostic report — a single silent upload of a device's
entire local event log (screen opens, every button tap, validation
failures, errors), triggered manually from the app when a shop is working
with support on a specific problem.

Separate from /events/sync (app/routes/user_event_log_routes.py), which
streams only the low-volume error/validation subset automatically in the
background. This endpoint is one-shot, higher-volume, and NOT called
automatically — see Android util/DiagnosticReportUploader.kt.

  • POST /diagnostic-reports/upload        — shop-scoped, one-shot upload
  • GET  /admin/diagnostic-reports         — list a shop's recent reports
  • GET  /admin/diagnostic-reports/{id}    — full event payload for one report
  • DELETE /admin/diagnostic-reports       — on-demand admin cleanup

Retention: rows are auto-deleted after 14 days by a daily scheduled job
(app/services/diagnostic_report_cleanup_service.py) — much shorter than
user_event_logs' 90 days, since a report is only useful while a specific
investigation is active.
"""
import logging
from datetime import timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_shop, require_admin
from app.models.diagnostic_report import DiagnosticReport
from app.util.time_utils import local_now, epoch_ms_to_local
from app.schemas.diagnostic_report_schema import (
    DiagnosticReportUploadRequest,
    DiagnosticReportUploadResponse,
    DiagnosticReportListResponse,
    DiagnosticReportSummary,
    DiagnosticReportDetail,
)

router = APIRouter(tags=["Diagnostic Report"])
logger = logging.getLogger(__name__)


@router.post("/diagnostic-reports/upload", response_model=DiagnosticReportUploadResponse)
def upload_diagnostic_report(
    payload: DiagnosticReportUploadRequest,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop),
):
    """
    One shot: store the entire payload as a single JSON blob row rather
    than exploding it into individual rows like /events/sync does — this
    is read once per investigation, not filtered/queried like the main
    event table, so there's no benefit to normalizing it.

    Each event's created_at arrives as raw device epoch-millis (see
    UserEventDto) — convert it to a readable local-timezone timestamp
    string before storing, the same way /events/sync does via
    epoch_ms_to_local, instead of dumping the unreadable epoch number
    straight into the JSON blob.
    """
    events_json = []
    for e in payload.events:
        row = e.model_dump()
        row["created_at"] = (
            epoch_ms_to_local(int(e.created_at)).isoformat()
            if e.created_at
            else local_now().isoformat()
        )
        events_json.append(row)
    report = DiagnosticReport(
        shop_id=current_shop.id,
        events=events_json,
        event_count=len(events_json),
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    logger.info(
        "Diagnostic report uploaded: shop_id=%s report_id=%s event_count=%d",
        current_shop.id, report.id, report.event_count,
    )

    return DiagnosticReportUploadResponse(
        report_id=report.id,
        event_count=report.event_count,
        message=f"{report.event_count} event(s) uploaded",
    )


@router.get(
    "/admin/diagnostic-reports",
    response_model=DiagnosticReportListResponse,
    dependencies=[Depends(require_admin)],
)
def list_diagnostic_reports(
    shop_id: int = Query(..., description="Shop to list diagnostic reports for"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Summaries only (no event payload) — pick a report, then fetch it by id."""
    q = (
        db.query(DiagnosticReport)
        .filter(DiagnosticReport.shop_id == shop_id)
        .order_by(DiagnosticReport.created_at.desc())
        .limit(limit)
    )
    reports = q.all()
    return DiagnosticReportListResponse(
        reports=[DiagnosticReportSummary.model_validate(r) for r in reports],
        total=len(reports),
    )


@router.get(
    "/admin/diagnostic-reports/{report_id}",
    response_model=DiagnosticReportDetail,
    dependencies=[Depends(require_admin)],
)
def get_diagnostic_report(report_id: int, db: Session = Depends(get_db)):
    report = db.query(DiagnosticReport).filter(DiagnosticReport.id == report_id).first()
    if report is None:
        raise HTTPException(status_code=404, detail="Diagnostic report not found")
    return DiagnosticReportDetail.model_validate(report)


@router.delete(
    "/admin/diagnostic-reports",
    dependencies=[Depends(require_admin)],
)
def delete_diagnostic_reports(
    shop_id: Optional[int] = Query(None, description="Delete all reports for this shop"),
    report_ids: Optional[List[int]] = Query(None, description="Delete these specific report ids"),
    older_than_days: Optional[int] = Query(None, ge=1, description="Delete everything older than N days"),
    db: Session = Depends(get_db),
):
    """Same one-of-three-filters convention as DELETE /admin/events."""
    filters_given = sum(x is not None for x in (shop_id, report_ids, older_than_days))
    if filters_given != 1:
        return {
            "deleted_count": 0,
            "message": "Provide exactly one of shop_id, report_ids, or older_than_days.",
        }

    q = db.query(DiagnosticReport)
    if shop_id is not None:
        q = q.filter(DiagnosticReport.shop_id == shop_id)
    elif report_ids is not None:
        q = q.filter(DiagnosticReport.id.in_(report_ids))
    else:
        cutoff = utc_now() - timedelta(days=older_than_days)
        q = q.filter(DiagnosticReport.created_at < cutoff)

    deleted_count = q.delete(synchronize_session=False)
    db.commit()

    logger.info("Admin deleted %d diagnostic_report row(s)", deleted_count)
    return {"deleted_count": deleted_count, "message": f"Deleted {deleted_count} report(s)"}
