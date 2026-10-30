"""Password hashing, token issuance and keyed hashing helpers."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.config import get_settings

_hasher = PasswordHasher()
JWT_ALGORITHM = "HS256"
ACCESS_COOKIE = "ns_access"
REFRESH_COOKIE = "ns_refresh"
CSRF_COOKIE = "ns_csrf"
CSRF_HEADER = "x-csrf-token"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def keyed_hash(value: str, purpose: str) -> str:
    """HMAC-SHA256 with the app secret. Used for refresh tokens, reset tokens and IPs."""
    key = f"{get_settings().secret_key}:{purpose}".encode()
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()


def new_opaque_token() -> str:
    return secrets.token_urlsafe(32)


def create_access_token(user_id: uuid.UUID, role: str, session_id: uuid.UUID) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "sid": str(session_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_ttl_minutes)).timestamp()),
        "typ": "access",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=JWT_ALGORITHM)


def create_scoped_token(subject: str, scope: str, ttl_seconds: int, **claims: Any) -> str:
    """Short-lived token for a single purpose (e.g. opening a voice WebSocket)."""
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "typ": scope,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
        "jti": secrets.token_hex(8),
        **claims,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=JWT_ALGORITHM)


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    payload = jwt.decode(token, get_settings().secret_key, algorithms=[JWT_ALGORITHM])
    if payload.get("typ") != expected_type:
        raise jwt.InvalidTokenError("unexpected token type")
    return payload


def hash_ip(ip: str | None) -> str | None:
    return keyed_hash(ip, "ip")[:32] if ip else None


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
