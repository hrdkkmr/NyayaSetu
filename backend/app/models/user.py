from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin
from app.db.types import GUID
from app.models.enums import Language, UserRole


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(20))
    password_hash: Mapped[str] = mapped_column(String(255))
    # Google account subject ("sub" claim) once the user has signed in with Google.
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(32), default=UserRole.CITIZEN, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deletion_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    preferences: Mapped[UserPreferences] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan", lazy="selectin"
    )


class UserPreferences(TimestampMixin, Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    language: Mapped[str] = mapped_column(String(8), default=Language.EN)
    text_scale: Mapped[float] = mapped_column(Float, default=1.0)
    high_contrast: Mapped[bool] = mapped_column(Boolean, default=False)
    reduce_motion: Mapped[bool] = mapped_column(Boolean, default=False)
    voice_provider: Mapped[str] = mapped_column(String(32), default="browser")
    voice_speaker: Mapped[str | None] = mapped_column(String(64))
    speech_rate: Mapped[float] = mapped_column(Float, default=1.0)
    autoplay_voice: Mapped[bool] = mapped_column(Boolean, default=True)
    # Consent flags. Defaults are privacy-preserving: nothing optional is on until the user opts in.
    consent_store_transcripts: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_store_audio: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_external_ai: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_document_storage: Mapped[bool] = mapped_column(Boolean, default=False)
    consents_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="preferences")


class AuthSession(IdMixin, Base):
    __tablename__ = "auth_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    user_agent: Mapped[str | None] = mapped_column(String(300))
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PasswordResetToken(IdMixin, Base):
    __tablename__ = "password_reset_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Wrong one-time codes entered; the code is consumed at PASSWORD_RESET_MAX_ATTEMPTS.
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
