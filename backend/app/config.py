"""Application configuration loaded from environment variables.

Every external integration is optional. A missing credential disables that
integration and is surfaced through the integration health endpoint instead of
crashing the application.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_prefix="",
        extra="ignore",
        case_sensitive=False,
        env_ignore_empty=True,
    )

    # --- Core -----------------------------------------------------------------
    environment: Literal["development", "test", "production"] = "development"
    app_name: str = "NyayaSetu"
    secret_key: str = Field(default="dev-insecure-change-me", min_length=16)
    database_url: str = f"sqlite+aiosqlite:///{(BACKEND_ROOT / 'nyayasetu.db').as_posix()}"
    redis_url: str | None = None
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    public_app_url: str = "http://localhost:3000"
    log_level: str = "INFO"

    # --- Auth -----------------------------------------------------------------
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 14
    # Password reset uses a 6-digit one-time code sent by email.
    password_reset_ttl_minutes: int = 10
    password_reset_max_attempts: int = 5
    cookie_secure: bool = False
    cookie_domain: str | None = None
    # When true, password reset tokens are returned in the API response (development only).
    expose_dev_reset_tokens: bool = False
    # "Sign in with Google" (Google Identity Services). Unset = the button is hidden.
    google_client_id: str | None = None

    # --- Email (password reset, reminders) ---------------------------------------
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "NyayaSetu <no-reply@localhost>"
    smtp_starttls: bool = True

    # --- Rate limiting ----------------------------------------------------------
    rate_limit_per_minute: int = 120
    auth_rate_limit_per_minute: int = 10

    # --- Storage ----------------------------------------------------------------
    storage_backend: Literal["local", "s3"] = "local"
    local_storage_path: str = str(BACKEND_ROOT / "var" / "storage")
    s3_bucket: str | None = None
    s3_endpoint_url: str | None = None
    s3_region: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    max_upload_mb: int = 20
    # 32-byte key, base64. Derived from SECRET_KEY when unset (set it explicitly in production).
    storage_encryption_key: str | None = None

    # --- LLM ----------------------------------------------------------------------
    llm_provider: Literal["anthropic", "openai_compatible", "offline"] = "anthropic"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5-5"
    anthropic_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    anthropic_enable_fallbacks: bool = True
    # Any OpenAI-compatible Chat Completions API (e.g. xAI Grok, Groq).
    llm_api_base: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    # Optional second model on the same API, tried once when the primary is rate-limited or down.
    llm_fallback_model: str | None = None
    llm_timeout_seconds: float = 90.0

    # --- Embeddings -------------------------------------------------------------
    embedding_provider: Literal["hashing", "openai_compatible"] = "hashing"
    embedding_dimensions: int = 384
    embedding_api_base: str | None = None
    embedding_api_key: str | None = None
    embedding_model: str | None = None

    # --- Speech -------------------------------------------------------------------
    sarvam_api_key: str | None = None
    sarvam_api_base: str = "https://api.sarvam.ai"
    # Per docs.sarvam.ai (checked 2026-10-30): STT saaras:v4 / saaras:v3; TTS bulbul:v3 (API default),
    # bulbul:v4-flash (persona speaker IDs) or bulbul:v2.
    sarvam_stt_model: str = "saaras:v4"
    sarvam_tts_model: str = "bulbul:v3"
    sarvam_tts_speaker_hi: str = "priya"
    sarvam_tts_speaker_en: str = "priya"

    # --- OCR ------------------------------------------------------------------------
    ocr_provider: Literal["none", "tesseract"] = "tesseract"
    tesseract_cmd: str | None = None

    # --- Filing ---------------------------------------------------------------------
    ejagriti_base_url: str = "https://e-jagriti.gov.in"
    enable_browser_assist: bool = False
    browser_assist_headless: bool = False

    # --- Observability -------------------------------------------------------------
    sentry_dsn: str | None = None
    otel_exporter_otlp_endpoint: str | None = None

    # --- Legal knowledge --------------------------------------------------------------
    legal_manifest_path: str = str(BACKEND_ROOT / "data" / "legal_sources" / "manifest.yaml")
    legal_fetch_live: bool = False

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            if value.strip().startswith("["):
                return value
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("database_url", mode="before")
    @classmethod
    def _async_driver(cls, value: object) -> object:
        # Hosts (e.g. Render) hand out postgres:// or postgresql:// URLs; the app needs asyncpg.
        if isinstance(value, str):
            for prefix in ("postgres://", "postgresql://"):
                if value.startswith(prefix):
                    return "postgresql+asyncpg://" + value[len(prefix):]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def llm_configured(self) -> bool:
        if self.llm_provider == "anthropic":
            return bool(self.anthropic_api_key)
        if self.llm_provider == "openai_compatible":
            return bool(self.llm_api_base and self.llm_api_key and self.llm_model)
        return False

    @property
    def llm_description(self) -> str:
        if self.llm_provider == "openai_compatible":
            return f"{self.llm_model} via {self.llm_api_base}"
        return f"Anthropic {self.anthropic_model}"

    def validate_for_production(self) -> list[str]:
        """Return configuration problems that must block a production start."""
        problems: list[str] = []
        if self.secret_key.startswith("dev-") or len(self.secret_key) < 32:
            problems.append("SECRET_KEY must be a random value of at least 32 characters")
        if not self.cookie_secure:
            problems.append("COOKIE_SECURE must be true in production")
        if self.is_sqlite:
            problems.append("DATABASE_URL must point to PostgreSQL in production")
        if self.expose_dev_reset_tokens:
            problems.append("EXPOSE_DEV_RESET_TOKENS must be false in production")
        if any(origin == "*" for origin in self.cors_origins):
            problems.append("CORS_ORIGINS must not contain '*'")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()
