"""
Thin accessor for the global app_config key/value table. Every key used
by the onboarding/subscription/trial feature is listed here with its
default, so a fresh deploy (no rows yet) behaves sensibly rather than
raising on a missing key.
"""
from sqlalchemy.orm import Session
from app.models.app_config import AppConfig

DEFAULTS = {
    # Free trial length in days. Change this value in the DB (or via a
    # future admin endpoint) to change trial length app-wide — never
    # hardcode this number in the Android app.
    "trial_duration_days": "15",

    # Kill switch: "true" enforces the onboarding gate (Splash/
    # MainActivity/ChangePasswordActivity all redirect incomplete shops
    # into OnboardingActivity). Set to "false" to let everyone straight
    # into Dashboard without shipping a new APK, if a bug is found in
    # the wizard post-launch.
    "onboarding_enforcement_enabled": "true",

    # Terms version a shop's terms_accepted_at/terms_version must match
    # to count as current. Bump this to force re-acceptance after a
    # terms update.
    "required_terms_version": "1.0",
}


def get_config(db: Session, key: str) -> str:
    row = db.query(AppConfig).filter(AppConfig.key == key).first()
    if row is not None:
        return row.value
    if key in DEFAULTS:
        return DEFAULTS[key]
    raise KeyError(f"Unknown app_config key: {key}")


def get_config_bool(db: Session, key: str) -> bool:
    return get_config(db, key).strip().lower() == "true"


def get_config_int(db: Session, key: str) -> int:
    return int(get_config(db, key))


def set_config(db: Session, key: str, value: str) -> None:
    row = db.query(AppConfig).filter(AppConfig.key == key).first()
    if row is None:
        row = AppConfig(key=key, value=value)
        db.add(row)
    else:
        row.value = value
    db.commit()
