from sqlalchemy import Column, Integer, ForeignKey, DateTime, JSON
from app.database import Base
from app.util.time_utils import local_now


class DiagnosticReport(Base):
    """
    A one-shot, on-demand dump of a single device's FULL local event log
    (every screen open, every button tap, every validation failure, every
    error — not just the low-volume error/validation subset that syncs
    automatically into user_event_logs).

    This deliberately does NOT sync in the background — the volume of a
    full click-level trail is too high to stream continuously without
    bloating the main table. Instead, the shop owner (or support, talking
    them through it) triggers a single "Send diagnostic report" action in
    the app, which silently uploads the current local event log here in
    one shot. Nothing is shown to the shop owner and nothing goes through
    a share sheet — see Android util/DiagnosticReportUploader.kt.

    Short-lived on purpose: only useful while a specific report is being
    actively investigated, so it's cleaned up much sooner than the 90-day
    user_event_logs retention — see
    app/services/diagnostic_report_cleanup_service.py.
    """
    __tablename__ = "diagnostic_reports"

    id = Column(Integer, primary_key=True, index=True)

    # Indexed — support pulls a shop's most recent report(s); cleanup job
    # filters by created_at.
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False, index=True)

    # The full local event trail at upload time, as a JSON array of
    # {event_type, screen, detail, created_at} objects — same shape as
    # UserEventLog rows, just not exploded into individual DB rows since
    # this is read once per investigation, not queried/filtered like the
    # main table.
    events = Column(JSON, nullable=False)

    # How many events were in the payload — quick glance without parsing
    # the JSON, useful when listing a shop's reports.
    event_count = Column(Integer, nullable=False, default=0)

    # Wall-clock time the report was uploaded, in the shop's timezone
    # (APP_TZ) — this is a Bucket-A "shown to a human" timestamp, same
    # convention as Bill.created_at, not a Bucket-B sync cursor. Admin
    # reads this directly as "when was this uploaded", so it needs to be
    # in local time, not UTC.
    created_at = Column(DateTime, default=local_now, nullable=False, index=True)
