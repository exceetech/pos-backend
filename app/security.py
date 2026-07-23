import os
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from app.util.time_utils import utc_now
from fastapi import HTTPException, status

# ── Password hashing ──────────────────────────────────────────────────────────

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# ── JWT ───────────────────────────────────────────────────────────────────────

# Report 5 fix: was a hardcoded literal — anyone with repo access could forge
# a valid token for any shop, permanently, with no way to rotate it short of
# editing source and redeploying. Now read from the environment, matching the
# EMAIL_ADDRESS / EMAIL_PASSWORD pattern already used elsewhere (email_service.py).
# The hardcoded string is kept ONLY as a fallback so already-deployed
# environments that haven't set JWT_SECRET_KEY yet don't break on this
# deploy — set JWT_SECRET_KEY in the environment and this fallback stops
# mattering. Every previously-issued token was signed with the old literal
# either way, so this alone doesn't invalidate anything already out there.
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "eXCeeTechSecretKeyForJWTGeneration")
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
