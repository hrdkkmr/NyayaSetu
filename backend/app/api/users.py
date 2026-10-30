from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import serializers as ser
from app.core.audit import record_audit
from app.core.deps import RequestContext, get_context
from app.core.errors import AppError, NotFoundError
from app.core.security import hash_password, verify_password
from app.db.base import utcnow
from app.db.session import get_db
from app.models import AuthSession, Case, CaseFact, Conversation, ConversationMessage, UploadedDocument
from app.schemas.auth import (
    PasswordChangeRequest,
    PreferencesOut,
    PreferencesUpdate,
    SessionOut,
    UserOut,
    UserUpdate,
)
from app.schemas.common import Message
from app.services.storage import purge_voice_audio

router = APIRouter(prefix="/users/me", tags=["users"])

CONSENT_FIELDS = {"consent_store_transcripts", "consent_store_audio", "consent_external_ai", "consent_document_storage"}


@router.get("", response_model=UserOut)
async def get_me(ctx: RequestContext = Depends(get_context), db: AsyncSession = Depends(get_db)) -> UserOut:
    await db.refresh(ctx.user, attribute_names=["preferences"])
    return UserOut.model_validate(ctx.user)


@router.patch("", response_model=UserOut)
async def update_me(payload: UserUpdate, ctx: RequestContext = Depends(get_context),
                    db: AsyncSession = Depends(get_db)) -> UserOut:
    if payload.full_name is not None:
        ctx.user.full_name = payload.full_name.strip()
    if payload.phone is not None:
        ctx.user.phone = payload.phone or None
    await record_audit(db, action="user.update", actor_user_id=ctx.user.id, ip_hash=ctx.ip_hash)
    await db.flush()
    await db.refresh(ctx.user, attribute_names=["preferences", "updated_at"])
    return UserOut.model_validate(ctx.user)


@router.patch("/preferences", response_model=PreferencesOut)
async def update_preferences(payload: PreferencesUpdate, ctx: RequestContext = Depends(get_context),
                             db: AsyncSession = Depends(get_db)) -> PreferencesOut:
    await db.refresh(ctx.user, attribute_names=["preferences"])
    prefs = ctx.user.preferences
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(prefs, key, value)
    if changes.get("consent_store_audio") is False:
        await purge_voice_audio(db, ctx.user.id)
    if CONSENT_FIELDS & changes.keys():
        prefs.consents_updated_at = utcnow()
        await record_audit(db, action="user.consent_change", actor_user_id=ctx.user.id, ip_hash=ctx.ip_hash,
                           meta={k: changes[k] for k in CONSENT_FIELDS & changes.keys()})
    await db.flush()
    return PreferencesOut.model_validate(prefs)


@router.post("/password", response_model=Message)
async def change_password(payload: PasswordChangeRequest, ctx: RequestContext = Depends(get_context),
                          db: AsyncSession = Depends(get_db)) -> Message:
    if not verify_password(payload.current_password, ctx.user.password_hash):
        raise AppError("Your current password is incorrect.", code="invalid_password")
    ctx.user.password_hash = hash_password(payload.new_password)
    await db.execute(update(AuthSession).where(
        AuthSession.user_id == ctx.user.id, AuthSession.id != ctx.session_id, AuthSession.revoked_at.is_(None)
    ).values(revoked_at=utcnow()))
    await record_audit(db, action="user.password_change", actor_user_id=ctx.user.id, ip_hash=ctx.ip_hash)
    return Message(message="Password changed. Other devices have been signed out.")


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(ctx: RequestContext = Depends(get_context), db: AsyncSession = Depends(get_db)) -> list[SessionOut]:
    rows = (await db.scalars(select(AuthSession).where(
        AuthSession.user_id == ctx.user.id, AuthSession.revoked_at.is_(None)).order_by(AuthSession.last_used_at.desc()))).all()
    return [SessionOut(id=s.id, user_agent=s.user_agent, created_at=s.created_at, last_used_at=s.last_used_at,
                       expires_at=s.expires_at, current=s.id == ctx.session_id) for s in rows]


@router.delete("/sessions/{session_id}", response_model=Message)
async def revoke_session(session_id: uuid.UUID, ctx: RequestContext = Depends(get_context),
                         db: AsyncSession = Depends(get_db)) -> Message:
    session = await db.get(AuthSession, session_id)
    if session is None or session.user_id != ctx.user.id:
        raise NotFoundError("Session not found.")
    session.revoked_at = utcnow()
    await record_audit(db, action="user.session_revoke", actor_user_id=ctx.user.id, ip_hash=ctx.ip_hash)
    return Message(message="Session signed out.")


@router.get("/export")
async def export_data(ctx: RequestContext = Depends(get_context), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Machine-readable export of the user's data (uploaded file contents are downloadable separately)."""
    user = ctx.user
    cases = (await db.scalars(select(Case).where(Case.user_id == user.id))).all()
    out_cases = []
    for case in cases:
        facts = (await db.scalars(select(CaseFact).where(CaseFact.case_id == case.id))).all()
        convs = (await db.scalars(select(Conversation).where(Conversation.case_id == case.id))).all()
        messages: list[dict[str, Any]] = []
        for conv in convs:
            msgs = (await db.scalars(select(ConversationMessage).where(ConversationMessage.conversation_id == conv.id)
                                     .order_by(ConversationMessage.created_at))).all()
            messages.extend(ser.message(m) for m in msgs)
        uploads = (await db.scalars(select(UploadedDocument).where(UploadedDocument.case_id == case.id))).all()
        out_cases.append({**ser.case_summary(case), "facts": [ser.fact(f) for f in facts], "messages": messages,
                          "uploads": [ser.upload(u) for u in uploads]})
    await record_audit(db, action="user.data_export", actor_user_id=user.id, ip_hash=ctx.ip_hash)
    return {"user": {"id": str(user.id), "email": user.email, "full_name": user.full_name, "phone": user.phone,
                     "created_at": ser.iso(user.created_at)}, "cases": out_cases, "exported_at": ser.iso(utcnow())}


@router.post("/deletion-request", response_model=Message)
async def request_deletion(ctx: RequestContext = Depends(get_context), db: AsyncSession = Depends(get_db)) -> Message:
    ctx.user.deletion_requested_at = utcnow()
    await record_audit(db, action="user.deletion_requested", actor_user_id=ctx.user.id, ip_hash=ctx.ip_hash)
    return Message(message="Your deletion request has been recorded. Your account and data will be deleted "
                           "within 30 days unless you cancel the request.")


@router.delete("/deletion-request", response_model=Message)
async def cancel_deletion(ctx: RequestContext = Depends(get_context), db: AsyncSession = Depends(get_db)) -> Message:
    ctx.user.deletion_requested_at = None
    await record_audit(db, action="user.deletion_cancelled", actor_user_id=ctx.user.id, ip_hash=ctx.ip_hash)
    return Message(message="Your deletion request has been cancelled.")
