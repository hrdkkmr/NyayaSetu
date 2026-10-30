from __future__ import annotations

import uuid
from datetime import UTC, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.audit import record_audit
from app.core.deps import RequestContext, get_context
from app.core.errors import AppError, AuthError, ConflictError
from app.core.ratelimit import client_ip, rate_limit_account, rate_limit_auth
from app.core.security import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    REFRESH_COOKIE,
    create_access_token,
    hash_ip,
    hash_password,
    keyed_hash,
    new_opaque_token,
    password_needs_rehash,
    verify_password,
)
from app.db.base import utcnow
from app.db.session import get_db
from app.models import AuthSession, PasswordResetToken, User, UserPreferences
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    PasswordForgotRequest,
    PasswordResetRequest,
    RefreshRequest,
    RegisterRequest,
    UserOut,
)
from app.schemas.common import Message
from app.services.email import email_configured, send_email

router = APIRouter(prefix="/auth", tags=["auth"])

# A fixed hash lets failed logins for unknown emails take as long as real ones.
_DUMMY_HASH = hash_password("timing-equaliser-not-a-real-password-1")


def _wants_tokens(request: Request) -> bool:
    """Non-browser clients ask for tokens in the body via this header."""
    return request.headers.get("x-client-type", "").lower() in {"mobile", "native"}


def _set_auth_cookies(response: Response, access: str, refresh: str, csrf: str) -> None:
    s = get_settings()
    response.set_cookie(
        ACCESS_COOKIE, access, httponly=True, max_age=s.access_token_ttl_minutes * 60,
        path="/", secure=s.cookie_secure, samesite="lax", domain=s.cookie_domain,
    )
    response.set_cookie(
        REFRESH_COOKIE, refresh, httponly=True, max_age=s.refresh_token_ttl_days * 86400,
        path="/api/v1/auth", secure=s.cookie_secure, samesite="lax", domain=s.cookie_domain,
    )
    # Readable by JS so the client can echo it in the X-CSRF-Token header.
    response.set_cookie(
        CSRF_COOKIE, csrf, httponly=False, max_age=s.refresh_token_ttl_days * 86400,
        path="/", secure=s.cookie_secure, samesite="lax", domain=s.cookie_domain,
    )


def _clear_auth_cookies(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(ACCESS_COOKIE, path="/", domain=s.cookie_domain)
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth", domain=s.cookie_domain)
    response.delete_cookie(CSRF_COOKIE, path="/", domain=s.cookie_domain)


async def _issue_session(
    db: AsyncSession, user: User, request: Request, response: Response
) -> AuthResponse:
    s = get_settings()
    now = utcnow()
    refresh = new_opaque_token()
    session = AuthSession(
        user_id=user.id,
        refresh_token_hash=keyed_hash(refresh, "refresh"),
        user_agent=(request.headers.get("user-agent") or "")[:300] or None,
        ip_hash=hash_ip(client_ip(request)),
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(days=s.refresh_token_ttl_days),
    )
    db.add(session)
    await db.flush()
    access = create_access_token(user.id, user.role, session.id)
    csrf = new_opaque_token()
    _set_auth_cookies(response, access, refresh, csrf)
    await db.refresh(user, attribute_names=["preferences"])
    body = AuthResponse(user=UserOut.model_validate(user), csrf_token=csrf)
    if _wants_tokens(request):
        body.access_token = access
        body.refresh_token = refresh
    return body


@router.post("/register", response_model=AuthResponse, status_code=201,
             dependencies=[Depends(rate_limit_auth)])
async def register(
    payload: RegisterRequest, request: Request, response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    email = payload.email.lower()
    if await db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise ConflictError("An account with this email already exists.", code="email_taken")
    user = User(
        email=email,
        full_name=payload.full_name.strip(),
        phone=payload.phone,
        password_hash=hash_password(payload.password),
    )
    user.preferences = UserPreferences(language=payload.language)
    db.add(user)
    await db.flush()
    await record_audit(db, action="auth.register", actor_user_id=user.id,
                       resource_type="user", resource_id=user.id,
                       ip_hash=hash_ip(client_ip(request)))
    return await _issue_session(db, user, request, response)


@router.post("/login", response_model=AuthResponse, dependencies=[Depends(rate_limit_auth)])
async def login(
    payload: LoginRequest, request: Request, response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    await rate_limit_account(payload.email)
    user = await db.scalar(select(User).where(func.lower(User.email) == payload.email.lower()))
    if user is None:
        verify_password(payload.password, _DUMMY_HASH)
        raise AuthError("Incorrect email or password.", code="invalid_credentials")
    if not verify_password(payload.password, user.password_hash) or not user.is_active:
        await record_audit(db, action="auth.login", actor_user_id=user.id, outcome="failure",
                           ip_hash=hash_ip(client_ip(request)))
        await db.commit()
        raise AuthError("Incorrect email or password.", code="invalid_credentials")
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)
    user.last_login_at = utcnow()
    await record_audit(db, action="auth.login", actor_user_id=user.id,
                       ip_hash=hash_ip(client_ip(request)))
    return await _issue_session(db, user, request, response)


@router.post("/refresh", response_model=AuthResponse, dependencies=[Depends(rate_limit_auth)])
async def refresh(
    request: Request, response: Response,
    payload: RefreshRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    token = (payload.refresh_token if payload else None) or request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise AuthError("Please sign in again.", code="refresh_missing")
    session = await db.scalar(
        select(AuthSession).where(AuthSession.refresh_token_hash == keyed_hash(token, "refresh"))
    )
    now = utcnow()
    if session is not None and session.revoked_at is not None:
        # A rotated (already used) refresh token was presented again: likely theft. End every session.
        await db.execute(update(AuthSession).where(AuthSession.user_id == session.user_id,
                                                   AuthSession.revoked_at.is_(None)).values(revoked_at=now))
        await record_audit(db, action="auth.refresh_reuse", actor_user_id=session.user_id, outcome="failure",
                           ip_hash=hash_ip(client_ip(request)))
        await db.commit()
    if session is None or session.revoked_at is not None:
        _clear_auth_cookies(response)
        raise AuthError("Please sign in again.", code="refresh_invalid")
    expires = session.expires_at if session.expires_at.tzinfo else session.expires_at.replace(tzinfo=UTC)
    if expires < now:
        _clear_auth_cookies(response)
        raise AuthError("Please sign in again.", code="refresh_expired")
    user = await db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise AuthError("This account is not active.", code="account_inactive")
    # Rotate atomically: only one concurrent request can consume a refresh token.
    rotated = await db.execute(
        update(AuthSession).where(AuthSession.id == session.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now).execution_options(synchronize_session=False)
    )
    if getattr(rotated, "rowcount", 1) != 1:
        raise AuthError("Please sign in again.", code="refresh_invalid")
    return await _issue_session(db, user, request, response)


@router.post("/logout", response_model=Message)
async def logout(
    response: Response,
    ctx: RequestContext = Depends(get_context),
    db: AsyncSession = Depends(get_db),
) -> Message:
    session = await db.get(AuthSession, ctx.session_id)
    if session and session.revoked_at is None:
        session.revoked_at = utcnow()
    await record_audit(db, action="auth.logout", actor_user_id=ctx.user.id, ip_hash=ctx.ip_hash)
    _clear_auth_cookies(response)
    return Message(message="Signed out.")


@router.post("/password/forgot", response_model=dict, dependencies=[Depends(rate_limit_auth)])
async def forgot_password(
    payload: PasswordForgotRequest, request: Request, background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    await rate_limit_account(payload.email)
    s = get_settings()
    generic: dict[str, object] = {
        "message": "If an account exists for this email, we have sent password reset instructions.",
    }
    user = await db.scalar(select(User).where(func.lower(User.email) == payload.email.lower()))
    if user is None or not user.is_active:
        return generic
    token = new_opaque_token()
    now = utcnow()
    db.add(PasswordResetToken(
        user_id=user.id, token_hash=keyed_hash(token, "reset"), created_at=now,
        expires_at=now + timedelta(minutes=s.password_reset_ttl_minutes),
    ))
    link = f"{s.public_app_url.rstrip('/')}/reset-password?token={token}"
    # Sent after the response so response time does not reveal whether the account exists.
    background.add_task(
        send_email, user.email, "Reset your NyayaSetu password",
        f"Use this link within {s.password_reset_ttl_minutes} minutes to reset your password:\n\n"
        f"{link}\n\nIf you did not ask for this, you can ignore this email.",
    )
    delivery = "queued" if email_configured() else "not_configured"
    await record_audit(db, action="auth.password_forgot", actor_user_id=user.id,
                       ip_hash=hash_ip(client_ip(request)), meta={"delivery": delivery})
    result: dict[str, object] = dict(generic)
    if s.expose_dev_reset_tokens and not s.is_production:
        result["dev_reset_token"] = token
        result["dev_delivery"] = delivery
    return result


@router.post("/password/reset", response_model=Message, dependencies=[Depends(rate_limit_auth)])
async def reset_password(payload: PasswordResetRequest, db: AsyncSession = Depends(get_db)) -> Message:
    record = await db.scalar(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == keyed_hash(payload.token, "reset")
        )
    )
    now = utcnow()
    if record is None or record.used_at is not None:
        raise AppError("This reset link is invalid or has already been used.", code="reset_invalid")
    expires = record.expires_at if record.expires_at.tzinfo else record.expires_at.replace(tzinfo=UTC)
    if expires < now:
        raise AppError("This reset link has expired. Please request a new one.", code="reset_expired")
    user = await db.get(User, record.user_id)
    if user is None:
        raise AppError("This reset link is invalid.", code="reset_invalid")
    user.password_hash = hash_password(payload.new_password)
    # Consume every outstanding reset link for this account, not just this one.
    await db.execute(update(PasswordResetToken).where(
        PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None)).values(used_at=now))
    # Sign out everywhere after a password reset.
    await db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    await record_audit(db, action="auth.password_reset", actor_user_id=user.id)
    return Message(message="Your password has been reset. Please sign in.")


@router.get("/me", response_model=UserOut)
async def me(ctx: RequestContext = Depends(get_context), db: AsyncSession = Depends(get_db)) -> UserOut:
    await db.refresh(ctx.user, attribute_names=["preferences"])
    return UserOut.model_validate(ctx.user)


def parse_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise AppError("Invalid identifier.", code="invalid_id") from exc
