from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import serializers as ser
from app.core.deps import RequestContext, get_context
from app.core.errors import NotFoundError
from app.db.base import utcnow
from app.db.session import get_db
from app.models import Notification

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
async def list_notifications(unread_only: bool = False, ctx: RequestContext = Depends(get_context),
                             db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
    stmt = select(Notification).where(Notification.user_id == ctx.user.id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    rows = (await db.scalars(stmt.order_by(Notification.created_at.desc()).limit(100))).all()
    return [ser.notification(n) for n in rows]


@router.post("/{notification_id}/read")
async def mark_read(notification_id: uuid.UUID, ctx: RequestContext = Depends(get_context),
                    db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    note = await db.scalar(select(Notification).where(Notification.id == notification_id,
                                                      Notification.user_id == ctx.user.id))
    if note is None:
        raise NotFoundError("Notification not found.")
    note.read_at = note.read_at or utcnow()
    return ser.notification(note)


@router.post("/read-all")
async def mark_all_read(ctx: RequestContext = Depends(get_context), db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    await db.execute(update(Notification).where(Notification.user_id == ctx.user.id,
                                                Notification.read_at.is_(None)).values(read_at=utcnow()))
    return {"message": "All notifications marked as read."}
