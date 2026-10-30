from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import get_settings
from app.db.base import Base, IdMixin, TimestampMixin
from app.db.types import GUID, EmbeddingVector, JSONType
from app.models.enums import VerificationStatus


class LegalSource(IdMixin, TimestampMixin, Base):
    """A publisher of official legal material (e.g. the Gazette of India)."""

    __tablename__ = "legal_sources"

    key: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    base_url: Mapped[str] = mapped_column(String(500))
    source_type: Mapped[str] = mapped_column(String(32))
    trust_level: Mapped[str] = mapped_column(String(32), default="official")


class LegalDocument(IdMixin, TimestampMixin, Base):
    __tablename__ = "legal_documents"

    source_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("legal_sources.id", ondelete="RESTRICT"), index=True
    )
    key: Mapped[str] = mapped_column(String(100), unique=True)
    title: Mapped[str] = mapped_column(String(400))
    doc_type: Mapped[str] = mapped_column(String(32))
    jurisdiction: Mapped[str] = mapped_column(String(64), default="IN")
    legal_domain: Mapped[str] = mapped_column(String(64), index=True)
    source_url: Mapped[str] = mapped_column(String(1000))
    publication_date: Mapped[date | None] = mapped_column(Date)
    effective_date: Mapped[date | None] = mapped_column(Date)
    effective_date_note: Mapped[str | None] = mapped_column(Text)
    identifier: Mapped[str | None] = mapped_column(String(120))
    version_label: Mapped[str | None] = mapped_column(String(120))
    amends: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    language: Mapped[str] = mapped_column(String(8), default="en")
    sha256: Mapped[str | None] = mapped_column(String(64))
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieval_method: Mapped[str | None] = mapped_column(String(32))
    verification_status: Mapped[str] = mapped_column(
        String(32), default=VerificationStatus.UNVERIFIED
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_note: Mapped[str | None] = mapped_column(Text)
    ingestion_status: Mapped[str] = mapped_column(String(32), default="pending")
    ingestion_error: Mapped[str | None] = mapped_column(Text)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)

    source: Mapped[LegalSource] = relationship(lazy="selectin")


class LegalChunk(IdMixin, Base):
    __tablename__ = "legal_chunks"
    __table_args__ = (Index("ix_legal_chunks_doc_ordinal", "document_id", "ordinal"),)

    document_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("legal_documents.id", ondelete="CASCADE")
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    section_ref: Mapped[str | None] = mapped_column(String(64), index=True)
    heading: Mapped[str | None] = mapped_column(String(400))
    chapter: Mapped[str | None] = mapped_column(String(200))
    text: Mapped[str] = mapped_column(Text)
    search_text: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer)
    page_start: Mapped[int | None] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(
        EmbeddingVector(get_settings().embedding_dimensions)
    )
    embedding_model: Mapped[str | None] = mapped_column(String(64))

    document: Mapped[LegalDocument] = relationship(lazy="selectin")


class LegalCitation(IdMixin, TimestampMixin, Base):
    """A legal chunk the research agent relied on for a specific case."""

    __tablename__ = "legal_citations"

    case_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("cases.id", ondelete="CASCADE"), index=True
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("legal_chunks.id", ondelete="CASCADE")
    )
    topic: Mapped[str] = mapped_column(String(64))
    query: Mapped[str] = mapped_column(Text)
    score: Mapped[float] = mapped_column(Float)
    explanation: Mapped[str | None] = mapped_column(Text)
    explanation_language: Mapped[str] = mapped_column(String(8), default="en")
    explanation_generated_by: Mapped[str] = mapped_column(String(32), default="template")

    chunk: Mapped[LegalChunk] = relationship(lazy="selectin")
