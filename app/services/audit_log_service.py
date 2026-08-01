from sqlalchemy.orm import Session
from app.models.audit_log import AuditLog


def log_event(db: Session, shop_id: int | None, event_type: str, detail: str = "", amount_paise: int | None = None) -> None:
    """
    Fire-and-forget-ish audit write. Deliberately swallows its own
    failures (logging a payment audit entry must never be the thing that
    breaks the actual payment flow) — commits independently of the
    caller's own transaction where possible, but if even that fails,
    logs to stderr and moves on rather than raising.
    """
    try:
        db.add(AuditLog(shop_id=shop_id, event_type=event_type, detail=detail, amount_paise=amount_paise))
        db.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Audit log write failed (event_type=%s): %s", event_type, e)
