from sqlalchemy import Column, Integer, String
from app.database import Base


class AppConfig(Base):
    """
    Global, admin-editable key/value config — not per-shop. Backs
    server-controlled values that must be changeable without an app
    release: trial length, the onboarding-enforcement kill switch, the
    currently-required terms version, etc.

    Deliberately a plain key/value table rather than one column per
    setting, so adding a new server-controlled toggle later is a row
    insert, not a migration. Read through get_config()/set_config() in
    app/services/app_config_service.py (Phase 1 also adds sane defaults
    on first read, so a missing row never crashes a caller).
    """
    __tablename__ = "app_config"

    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)
