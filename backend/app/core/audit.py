"""Audit logging. Never pass document text, transcripts, passwords or tokens in `meta`."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.models import AuditLog

_FORBIDDEN_META_KEYS = {"password", "token", "text", "content", "transcript", "secret", "api_key"}


def _scrub(meta: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in meta.items():
        if any(bad in key.lower() for bad in _FORBIDDEN_META_KEYS):
            clean[key] = "[redacted]"
        elif isinstance(value, str) and len(value) > 300:
            clean[key] = value[:300] + "…"
        else:
            clean[key] = value
    return clean


async def record_audit(
    db: AsyncSession,
    *,
    action: str,
    actor_user_id: uuid.UUID | None,
    actor_type: str = "user",
    resource_type: str | None = None,
    resource_id: uuid.UUID | str | None = None,
    case_id: uuid.UUID | None = None,
    ip_hash: str | None = None,
    outcome: str = "success",
    meta: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            created_at=utcnow(),
            actor_user_id=actor_user_id,
            actor_type=actor_type,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            case_id=case_id,
            ip_hash=ip_hash,
            outcome=outcome,
            meta=_scrub(meta or {}),
        )
    )
