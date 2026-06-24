from sqlalchemy import Boolean, Column, Integer, String, DateTime
from datetime import datetime
from app.database import Base
from app.util.time_utils import local_now


class Shop(Base):
    __tablename__ = "shops"

    id = Column(Integer, primary_key=True, index=True)

    shop_name = Column(String, nullable=False)
    owner_name = Column(String, nullable=False)

    email = Column(String, unique=True, index=True)
    phone = Column(String)

    # store settings
    store_address = Column(String)
    store_gstin = Column(String)

    password_hash = Column(String, nullable=True)

    # Valid values: PENDING | ACTIVE | ARCHIVED
    # IMPORTANT: default stays PENDING so OTP verification is not bypassed.
    status = Column(String, default="PENDING")
    is_first_login = Column(Boolean, default=True)

    created_at = Column(DateTime, default=local_now)

    device_id = Column(String, nullable=True)
    fcm_token = Column(String, nullable=True)

    reset_otp_hash = Column(String, nullable=True)
    reset_otp_expiry = Column(DateTime, nullable=True)
    reset_otp_attempts = Column(Integer, default=0)

    type = Column(String, default="general", nullable=False)

    # ── Workspace Rotation fields ──────────────────────────────────────────────
    # Preserved when a shop is archived so the original credentials can be
    # restored without losing them to the "archived_{ts}_" prefix.
    # Applied to DB via:
    #   ALTER TABLE shops ADD COLUMN IF NOT EXISTS original_phone VARCHAR;
    #   ALTER TABLE shops ADD COLUMN IF NOT EXISTS original_email VARCHAR;
    original_phone = Column(String, nullable=True, index=True)
    original_email = Column(String, nullable=True)

    # Monotonically increasing per workspace rotation / restore.
    # Embedded in JWT; get_current_shop() validates the JWT version matches DB.
    # Applied to DB via:
    #   ALTER TABLE shops ADD COLUMN IF NOT EXISTS workspace_version INTEGER DEFAULT 1;
    #   UPDATE shops SET workspace_version = 1 WHERE workspace_version IS NULL;
    workspace_version = Column(Integer, default=1, nullable=False)
