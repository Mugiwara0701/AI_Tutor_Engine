"""
Self-managed auth primitives: password hashing and our own JWT
issuance/verification. No Supabase Auth involved — this backend is the
source of truth for identity.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
from jose import jwt, JWTError

from app.config import settings


class TokenError(Exception):
    """Raised when a bearer token is missing, malformed, or expired."""


# ---------- Passwords ----------

# bcrypt's algorithm only uses the first 72 BYTES of input (not characters).
# We truncate defensively so multi-byte unicode passwords near the limit
# don't raise instead of just being handled sanely.
_BCRYPT_MAX_BYTES = 72


def hash_password(plain_password: str) -> str:
    password_bytes = plain_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    password_bytes = plain_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.checkpw(password_bytes, hashed_password.encode("utf-8"))


# ---------- JWT ----------

def create_access_token(subject: str, extra_claims: Optional[dict[str, Any]] = None) -> tuple[str, int]:
    """
    Mints a JWT signed with JWT_SECRET.

    Returns (token, expires_in_seconds).
    """
    expire_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    expire_at = datetime.now(timezone.utc) + expire_delta

    payload: dict[str, Any] = {"sub": subject, "exp": expire_at}
    if extra_claims:
        payload.update(extra_claims)

    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token, int(expire_delta.total_seconds())


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError as exc:
        raise TokenError(f"Invalid or expired token: {exc}") from exc


def get_user_id_from_payload(payload: dict[str, Any]) -> Optional[str]:
    return payload.get("sub")