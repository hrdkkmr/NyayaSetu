"""Request dependencies: authentication, CSRF, roles and resource ownership.

Web clients authenticate with httpOnly cookies and must echo the CSRF cookie in
the `X-CSRF-Token` header on unsafe methods. Non-browser clients (the future
Android app) use `Authorization: Bearer <access token>` and are exempt from CSRF
because bearer tokens are not sent ambiently by browsers.
"""

from __future__ import annotations

import hmac
import uuid
from dataclasses import dataclass

import jwt
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.errors import AuthError, ForbiddenError, NotFoundError
from app.core.ratelimit import client_ip, limiter
from app.core.security import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    CSRF_HEADER,
    decode_token,
    hash_ip,
)
from app.db.base import utcnow
from app.db.session import get_db
from app.models import AuthSession, Case, User
from app.models.enums import UserRole

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass
class RequestContext:
    user: User
    session_id: uuid.UUID
    ip_hash: str | None
    user_agent: str | None
    via_cookie: bool


async def get_context(request: Request, db: AsyncSession = Depends(get_db)) -> RequestContext:
    token: str | None = None
    via_cookie = False
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    elif request.cookies.get(ACCESS_COOKIE):
        token = request.cookies[ACCESS_COOKIE]
        via_cookie = True
    if not token:
        raise AuthError("Please sign in to continue.")

    try:
        payload = decode_token(token, "access")
        user_id = uuid.UUID(payload["sub"])
        session_id = uuid.UUID(payload["sid"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise AuthError("Your session has expired. Please sign in again.", code="token_invalid") from exc

    if via_cookie and request.method not in SAFE_METHODS:
        header = request.headers.get(CSRF_HEADER, "")
        cookie = request.cookies.get(CSRF_COOKIE, "")
        if not header or not cookie or not hmac.compare_digest(header, cookie):
            raise ForbiddenError("Security check failed. Please refresh the page.", code="csrf_failed")

    session = await db.get(AuthSession, session_id)
    if session is None or session.revoked_at is not None or session.user_id != user_id:
        raise AuthError("Your session has ended. Please sign in again.", code="session_revoked")
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        from datetime import UTC

        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < utcnow():
        raise AuthError("Your session has expired. Please sign in again.", code="session_expired")

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise AuthError("This account is not active.", code="account_inactive")

    await limiter.hit(f"user:{user.id}", get_settings().rate_limit_per_minute)
    ip = client_ip(request)
    return RequestContext(
        user=user,
        session_id=session_id,
        ip_hash=hash_ip(ip),
        user_agent=(request.headers.get("user-agent") or "")[:300] or None,
        via_cookie=via_cookie,
    )


async def get_current_user(ctx: RequestContext = Depends(get_context)) -> User:
    return ctx.user


def require_roles(*roles: UserRole):  # type: ignore[no-untyped-def]
    async def _check(ctx: RequestContext = Depends(get_context)) -> RequestContext:
        if ctx.user.role not in {r.value for r in roles}:
            raise ForbiddenError("You do not have access to this area.")
        return ctx

    return _check


async def get_owned_case(db: AsyncSession, case_id: uuid.UUID, user: User) -> Case:
    """Load a case only if `user` owns it. Returns 404 (not 403) to avoid leaking existence."""
    case = await db.scalar(select(Case).where(Case.id == case_id, Case.user_id == user.id))
    if case is None:
        raise NotFoundError("Case not found.")
    return case
