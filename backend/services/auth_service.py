"""JWT creation and validation for verification chain and meeting access."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from config import get_settings

settings = get_settings()

TOKEN_VERIFY = "verify"
TOKEN_LIVENESS = "liveness"
TOKEN_MEETING = "meeting"
TOKEN_ACTIVE_CHALLENGE = "active_challenge"
TOKEN_ADMIN = "admin"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_token(
    claims: dict[str, Any],
    expires_minutes: int,
) -> str:
    payload = dict(claims)
    expire = _utc_now() + timedelta(minutes=expires_minutes)
    payload["exp"] = expire
    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )


def create_verify_token(user_id: int, email: str) -> str:
    return create_token(
        {
            "sub": str(user_id),
            "uid": user_id,
            "email": email,
            "typ": TOKEN_VERIFY,
        },
        settings.JWT_VERIFY_EXPIRE_MINUTES,
    )


def create_liveness_token(user_id: int) -> str:
    return create_token(
        {
            "sub": str(user_id),
            "uid": user_id,
            "typ": TOKEN_LIVENESS,
        },
        settings.JWT_LIVENESS_EXPIRE_MINUTES,
    )


def create_meeting_token(
    user_id: int,
    room_id: str | None = None,
    full_name: str | None = None,
    email: str | None = None,
) -> str:
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "uid": user_id,
        "typ": TOKEN_MEETING,
    }
    if full_name:
        payload["name"] = full_name
    if email:
        payload["email"] = email
    if room_id:
        payload["room_id"] = room_id
    return create_token(payload, settings.JWT_MEETING_EXPIRE_MINUTES)


def create_admin_session_token(username: str) -> str:
    return create_token(
        {
            "sub": username,
            "role": "admin",
            "typ": TOKEN_ADMIN,
        },
        settings.JWT_ADMIN_EXPIRE_MINUTES,
    )


def create_active_challenge_token(user_id: int, action: str) -> str:
    return create_token(
        {
            "sub": str(user_id),
            "uid": user_id,
            "typ": TOKEN_ACTIVE_CHALLENGE,
            "action": action,
        },
        settings.ACTIVE_LIVENESS_EXPIRE_MINUTES,
    )


def safe_decode(token: str) -> dict[str, Any] | None:
    try:
        return decode_token(token)
    except JWTError:
        return None


def require_token_type(payload: dict[str, Any], expected: str) -> bool:
    return payload.get("typ") == expected


def hash_password(password: str) -> str:
    """
    Hash password using PBKDF2-HMAC-SHA256 with random salt.
    Stored format: pbkdf2_sha256$<iterations>$<salt_b64>$<digest_b64>
    """
    iterations = 200_000
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    salt_b64 = base64.b64encode(salt).decode("ascii")
    digest_b64 = base64.b64encode(digest).decode("ascii")
    return f"pbkdf2_sha256${iterations}${salt_b64}${digest_b64}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, iter_s, salt_b64, digest_b64 = encoded.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        iterations = int(iter_s)
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected = base64.b64decode(digest_b64.encode("ascii"))
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(candidate, expected)
    except Exception:
        return False
