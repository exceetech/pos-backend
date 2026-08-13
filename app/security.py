import logging
import os
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from app.util.time_utils import utc_now
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

# ── Password hashing ──────────────────────────────────────────────────────────

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# ── JWT ───────────────────────────────────────────────────────────────────────

# Report 5 fix, tightened further ahead of hosting: this used to be a
# hardcoded literal with no env override, then a hardcoded literal kept
# as a FALLBACK when JWT_SECRET_KEY wasn't set. That fallback string is
# sitting in this source file — if this app is hosted without
# JWT_SECRET_KEY explicitly set, every login token gets signed with a
# secret anyone who has seen this repo already knows, which is a full
# auth bypass (forge a valid session for any shop_id), not just a
# degraded feature. Fail loudly at import instead — same fail-closed
# principle as require_admin() in dependencies.py for ADMIN_API_TOKEN.
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY is not set. Generate one (e.g. "
        "`python3 -c \"import secrets; print(secrets.token_urlsafe(48))\"`) "
        "and set it in the environment before starting the app."
    )
ALGORITHM  = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """
    Encode a JWT.  ``data`` must include ``shop_id``.
    Workspace-aware tokens should also include ``workspace_version``.
    """
    to_encode = data.copy()
    expire = (
        utc_now() + expires_delta
        if expires_delta
        else utc_now() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Return the full decoded payload dict. Raises HTTP 401 on failure."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


def verify_token(token: str) -> int:
    """
    Backwards-compatible helper — returns only shop_id (int).
    New code should prefer ``verify_token_full()`` for workspace-version checks.
    """
    payload = decode_token(token)
    shop_id = payload.get("shop_id")
    if shop_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing shop_id",
        )
    return int(shop_id)


def verify_token_full(token: str) -> dict:
    """
    Returns the full decoded payload dict.
    Guaranteed key: ``shop_id`` (int).
    Optional key:   ``workspace_version`` (int | None).
    """
    payload = decode_token(token)
    if payload.get("shop_id") is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing shop_id",
        )
    return payload
