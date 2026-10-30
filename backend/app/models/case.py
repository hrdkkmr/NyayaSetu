from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin
from app.db.types import GUID, JSONType
from app.models.enums import (
    CaseStatus,
    DeadlineStatus,
    FactProvenance,
    FactStatus,
    Language,
)


class Case(IdMixin, TimestampMixin, Base):
    __tablename__ = "cases"
    __table_args__ = (Index("ix_cases_user_status", "user_id", "status"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    reference: Mapped[str] = mapped_column(String(32), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(64), index=True)
    subcategory: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(40), default=CaseStatus.INTAKE)
    language: Mapped[str] = mapped_column(String(8), default=Language.EN)
    incident_summary: Mapped[str | None] = mapped_column(Text)
    incident_date: Mapped[date | None] = mapped_column(Date)
    financial_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    location_state: Mapped[str | None] = mapped_column(String(80))
    location_district: Mapped[str | None] = mapped_column(String(80))
    classification_confidence: Mapped[float | None] = mapped_column(Float)
    requires_human_review: Mapped[bool] = mapped_column(Boolean, default=True)
    # Agent-derived structured content: potential routes, missing information, next actions.
    analysis: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    parties: Mapped[list[CaseParty]] = relationship(
        back_populates="case", cascade="all, delete-orphan", order_by="CaseParty.created_at"
    )
    facts: Mapped[list[CaseFact]] = relationship(
        back_populates="case", cascade="all, delete-orphan", order_by="CaseFact.created_at"
    )


class CaseParty(IdMixin, TimestampMixin, Base):
    __tablename__ = "case_parties"

    case_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("cases.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(300))
    party_type: Mapped[str] = mapped_column(String(32), default="individual")
    address: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(320))
    provenance: Mapped[str] = mapped_column(String(32), default=FactProvenance.USER_STATED)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)

    case: Mapped[Case] = relationship(back_populates="parties")


class CaseFact(IdMixin, TimestampMixin, Base):
    """A single fact about a case, with explicit provenance.

    `provenance` distinguishes what the user said, what they explicitly confirmed,
    what was extracted from a document, and what the AI inferred.
    """

    __tablename__ = "case_facts"
    __table_args__ = (Index("ix_case_facts_case_key", "case_id", "key"),)

    case_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("cases.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(80))
    value: Mapped[str] = mapped_column(Text)
    value_type: Mapped[str] = mapped_column(String(20), default="text")
    provenance: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(20), default=FactStatus.ACTIVE)
    source_type: Mapped[str | None] = mapped_column(String(32))
    source_id: Mapped[str | None] = mapped_column(String(64))
    source_excerpt: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    case: Mapped[Case] = relationship(back_populates="facts")


class CaseUpdate(IdMixin, TimestampMixin, Base):
    __tablename__ = "case_updates"

    case_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("cases.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(String(32))
    update_type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str | None] = mapped_column(Text)
    event_date: Mapped[date | None] = mapped_column(Date)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    source_reference: Mapped[str | None] = mapped_column(String(500))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL")
    )


class Deadline(IdMixin, TimestampMixin, Base):
    __tablename__ = "deadlines"
    __table_args__ = (Index("ix_deadlines_due_status", "due_date", "status"),)

    case_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("cases.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(300))
    due_date: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(20), default=DeadlineStatus.OPEN)
    source: Mapped[str] = mapped_column(String(32))
    basis: Mapped[str | None] = mapped_column(Text)
    citation_chunk_id: Mapped[uuid.UUID | None] = mapped_column(GUID())
    is_estimate: Mapped[bool] = mapped_column(Boolean, default=True)
    reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reminder_days_before: Mapped[int] = mapped_column(Integer, default=7)
