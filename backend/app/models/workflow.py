from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin
from app.db.types import GUID, JSONType
from app.models.enums import (
    ApprovalStatus,
    FilingStatus,
    JobStatus,
    StepStatus,
    WorkflowStatus,
)


class WorkflowInstance(IdMixin, TimestampMixin, Base):
    """Persistent checkpoint of a case's LangGraph workflow."""

    __tablename__ = "workflow_instances"

    case_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("cases.id", ondelete="CASCADE"), unique=True
    )
    workflow_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default=WorkflowStatus.RUNNING)
    current_node: Mapped[str | None] = mapped_column(String(64))
    state: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)


class WorkflowStep(IdMixin, TimestampMixin, Base):
    __tablename__ = "workflow_steps"

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("workflow_instances.id", ondelete="CASCADE"), index=True
    )
    step_key: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(300))
    title_hi: Mapped[str | None] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default=StepStatus.PENDING)
    owner: Mapped[str] = mapped_column(String(16), default="user")
    order_index: Mapped[int] = mapped_column(Integer)
    due_date: Mapped[date | None] = mapped_column(Date)
    source_refs: Mapped[list[str]] = mapped_column(JSONType, default=list)


class AgentExecution(IdMixin, TimestampMixin, Base):
    __tablename__ = "agent_executions"

    workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("workflow_instances.id", ondelete="CASCADE"), index=True
    )
    case_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("cases.id", ondelete="CASCADE"), index=True
    )
    agent: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(20))
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(64))
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    error: Mapped[str | None] = mapped_column(Text)


class Approval(IdMixin, TimestampMixin, Base):
    """An explicit user authorization for a consequential action.

    Binds the action to an exact document version (by content hash) so an
    approval cannot be reused for content the user never saw.
    """

    __tablename__ = "approvals"

    case_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("cases.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default=ApprovalStatus.PENDING)
    target_type: Mapped[str] = mapped_column(String(40))
    target_id: Mapped[uuid.UUID] = mapped_column(GUID())
    document_version_ids: Mapped[list[str]] = mapped_column(JSONType, default=list)
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    statement: Mapped[str] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))


class FilingRecord(IdMixin, TimestampMixin, Base):
    __tablename__ = "filing_records"

    case_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("cases.id", ondelete="CASCADE"), index=True
    )
    portal: Mapped[str] = mapped_column(String(40))
    mode: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(40), default=FilingStatus.PREPARING)
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("approvals.id", ondelete="SET NULL")
    )
    document_version_ids: Mapped[list[str]] = mapped_column(JSONType, default=list)
    # Acknowledgement is only stored when the user provides it or the portal returns it.
    acknowledgement_number: Mapped[str | None] = mapped_column(String(120))
    acknowledgement_source: Mapped[str | None] = mapped_column(String(32))
    acknowledgement_document_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("uploaded_documents.id", ondelete="SET NULL")
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checklist_state: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    portal_state: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    notes: Mapped[str | None] = mapped_column(Text)


class BackgroundJob(IdMixin, TimestampMixin, Base):
    __tablename__ = "background_jobs"

    kind: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(20), default=JobStatus.QUEUED, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
