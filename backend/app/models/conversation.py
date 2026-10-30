from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin
from app.db.types import GUID, JSONType
from app.models.enums import Language, Modality


class Conversation(IdMixin, TimestampMixin, Base):
    __tablename__ = "conversations"

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    case_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("cases.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200), default="New conversation")
    language: Mapped[str] = mapped_column(String(8), default=Language.EN)
    # When false, message content is not persisted (only a placeholder is stored).
    store_transcript: Mapped[bool] = mapped_column(Boolean, default=True)

    messages: Mapped[list[ConversationMessage]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ConversationMessage.created_at",
    )


class ConversationMessage(IdMixin, TimestampMixin, Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (Index("ix_messages_conv_created", "conversation_id", "created_at"),)

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("conversations.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(8))
    modality: Mapped[str] = mapped_column(String(8), default=Modality.TEXT)
    redacted: Mapped[bool] = mapped_column(Boolean, default=False)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class VoiceSession(IdMixin, TimestampMixin, Base):
    __tablename__ = "voice_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("conversations.id", ondelete="SET NULL")
    )
    stt_provider: Mapped[str] = mapped_column(String(32))
    tts_provider: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(20), default="active")
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stats: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    audio_stored: Mapped[bool] = mapped_column(Boolean, default=False)
    resume_token_hash: Mapped[str | None] = mapped_column(String(128))
    notes: Mapped[str | None] = mapped_column(Text)
