from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import ORMModel


def _check_password(value: str) -> str:
    if len(value) < 10:
        raise ValueError("Password must be at least 10 characters long")
    if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
        raise ValueError("Password must contain letters and numbers")
    return value


class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    password: str = Field(max_length=200)
    phone: str | None = Field(default=None, max_length=20)
    language: str = Field(default="en", pattern="^(en|hi)$")
    accept_terms: bool

    @field_validator("password")
    @classmethod
    def _password(cls, value: str) -> str:
        return _check_password(value)

    @field_validator("accept_terms")
    @classmethod
    def _terms(cls, value: bool) -> bool:
        if not value:
            raise ValueError("You must accept the terms and privacy notice")
        return value

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        digits = re.sub(r"[\s-]", "", value)
        if not re.fullmatch(r"\+?\d{10,13}", digits):
            raise ValueError("Enter a valid phone number")
        return digits


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=200)


class PasswordForgotRequest(BaseModel):
    email: EmailStr


class PasswordResetRequest(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    new_password: str = Field(max_length=200)

    @field_validator("new_password")
    @classmethod
    def _password(cls, value: str) -> str:
        return _check_password(value)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(max_length=200)

    @field_validator("new_password")
    @classmethod
    def _password(cls, value: str) -> str:
        return _check_password(value)


class PreferencesOut(ORMModel):
    language: str
    text_scale: float
    high_contrast: bool
    reduce_motion: bool
    voice_provider: str
    voice_speaker: str | None
    speech_rate: float
    autoplay_voice: bool
    consent_store_transcripts: bool
    consent_store_audio: bool
    consent_external_ai: bool
    consent_document_storage: bool
    consents_updated_at: datetime | None


class PreferencesUpdate(BaseModel):
    language: str | None = Field(default=None, pattern="^(en|hi)$")
    text_scale: float | None = Field(default=None, ge=0.85, le=1.6)
    high_contrast: bool | None = None
    reduce_motion: bool | None = None
    voice_provider: str | None = Field(default=None, pattern="^(browser|sarvam)$")
    voice_speaker: str | None = Field(default=None, max_length=64)
    speech_rate: float | None = Field(default=None, ge=0.6, le=1.5)
    autoplay_voice: bool | None = None
    consent_store_transcripts: bool | None = None
    consent_store_audio: bool | None = None
    consent_external_ai: bool | None = None
    consent_document_storage: bool | None = None


class UserOut(ORMModel):
    id: uuid.UUID
    email: str
    full_name: str
    phone: str | None
    role: str
    created_at: datetime
    deletion_requested_at: datetime | None
    preferences: PreferencesOut


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    phone: str | None = Field(default=None, max_length=20)


class AuthResponse(BaseModel):
    user: UserOut
    # Returned for non-browser clients. Browsers rely on httpOnly cookies instead.
    access_token: str | None = None
    refresh_token: str | None = None
    csrf_token: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


class SessionOut(BaseModel):
    id: uuid.UUID
    user_agent: str | None
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime
    current: bool
