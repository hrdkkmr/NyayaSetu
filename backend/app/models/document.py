from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin
from app.db.types import GUID, JSONType
from app.models.enums import DocumentStatus, GeneratedDocStatus


class UploadedDocument(IdMixin, TimestampMixin, Base):
    __tablename__ = "uploaded_documents"

    case_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("cases.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_key: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default=DocumentStatus.UPLOADED)
    document_class: Mapped[str | None] = mapped_column(String(64))
    page_count: Mapped[int | None] = mapped_column(Integer)
    security_flags: Mapped[list[str]] = mapped_column(JSONType, default=list)
    error: Mapped[str | None] = mapped_column(Text)

    extraction: Mapped[DocumentExtraction | None] = relationship(
        back_populates="document", uselist=False, cascade="all, delete-orphan", lazy="selectin"
    )


class DocumentExtraction(IdMixin, TimestampMixin, Base):
    __tablename__ = "document_extractions"

    document_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("uploaded_documents.id", ondelete="CASCADE"), unique=True
    )
    method: Mapped[str] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text, default="")
    language_hint: Mapped[str | None] = mapped_column(String(8))
    fields: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    injection_flags: Mapped[list[str]] = mapped_column(JSONType, default=list)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    document: Mapped[UploadedDocument] = relationship(back_populates="extraction")


class EvidenceItem(IdMixin, TimestampMixin, Base):
    __tablename__ = "evidence_items"

    case_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("cases.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("uploaded_documents.id", ondelete="SET NULL")
    )
    label: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    evidence_type: Mapped[str] = mapped_column(String(64), default="document")
    evidence_date: Mapped[date | None] = mapped_column(Date)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    confirmed_by_user: Mapped[bool] = mapped_column(Boolean, default=False)


class GeneratedDocument(IdMixin, TimestampMixin, Base):
    __tablename__ = "generated_documents"
    __table_args__ = (UniqueConstraint("case_id", "doc_type", name="uq_generated_case_type"),)

    case_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("cases.id", ondelete="CASCADE"), index=True
    )
    doc_type: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(300))
    language: Mapped[str] = mapped_column(String(8), default="en")
    status: Mapped[str] = mapped_column(String(20), default=GeneratedDocStatus.DRAFT)
    template_id: Mapped[str] = mapped_column(String(64))
    template_version: Mapped[str] = mapped_column(String(16))
    current_version: Mapped[int] = mapped_column(Integer, default=0)

    versions: Mapped[list[DocumentVersion]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentVersion.version_number",
    )


class DocumentVersion(IdMixin, TimestampMixin, Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("generated_document_id", "version_number", name="uq_docversion_number"),
    )

    generated_document_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("generated_documents.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    content: Mapped[dict[str, Any]] = mapped_column(JSONType)
    content_sha256: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(32))
    change_note: Mapped[str | None] = mapped_column(Text)
    source_trace: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    validation: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)

    document: Mapped[GeneratedDocument] = relationship(back_populates="versions")
