"""LLM provider abstraction.

Agents depend on `LLMProvider`, never on a vendor SDK directly. Two providers ship:

* `AnthropicProvider` - Claude via the official Anthropic SDK (structured outputs
  validated against Pydantic models, streaming text, server-side refusal fallbacks).
* `OfflineProvider` - reports itself unavailable. Agents then use their
  deterministic rule-based paths, so the product keeps working without credentials
  and never pretends an LLM produced an answer.

Tests inject a `ScriptedProvider` (see tests/fakes.py).
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Generic, Protocol, TypeVar

from pydantic import BaseModel

from app.config import get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMUnavailableError(RuntimeError):
    """No LLM is configured, or the provider failed after retries."""


class LLMRefusalError(RuntimeError):
    pass


@dataclass
class LLMResult(Generic[T]):
    value: T
    provider: str
    model: str | None
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    meta: dict[str, Any] = field(default_factory=dict)


class LLMProvider(Protocol):
    name: str
    model: str | None

    @property
    def available(self) -> bool: ...

    async def structured(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        schema: type[T],
        max_tokens: int = 4096,
    ) -> LLMResult[T]: ...

    def stream_text(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]: ...


class OfflineProvider:
    name = "offline"
    model: str | None = None

    @property
    def available(self) -> bool:
        return False

    async def structured(self, **_: Any) -> LLMResult[Any]:
        raise LLMUnavailableError("No LLM provider is configured")

    async def stream_text(self, **_: Any) -> AsyncIterator[str]:
        raise LLMUnavailableError("No LLM provider is configured")
        yield ""  # pragma: no cover - makes this an async generator


class AnthropicProvider:
    name = "anthropic"

    def __init__(self) -> None:
        import anthropic

        settings = get_settings()
        self._anthropic = anthropic
        self.model = settings.anthropic_model
        self._effort = settings.anthropic_effort
        self._fallbacks = settings.anthropic_enable_fallbacks
        self._client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            timeout=settings.llm_timeout_seconds,
            max_retries=2,
        )

    @property
    def available(self) -> bool:
        return True

    def _extra(self) -> dict[str, Any]:
        if self._fallbacks:
            return {"betas": [FALLBACK_BETA], "fallbacks": "default"}
        return {}

    async def structured(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        schema: type[T],
        max_tokens: int = 4096,
    ) -> LLMResult[T]:
        anthropic = self._anthropic
        started = time.perf_counter()
        try:
            response = await self._client.beta.messages.parse(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,  # type: ignore[arg-type]
                output_format=schema,
                output_config={"effort": self._effort},
                **self._extra(),
            )
        except anthropic.BadRequestError as exc:
            if self._fallbacks and "fallback" in str(exc).lower():
                # The account may not have the fallback beta; retry once without it.
                logger.warning("Fallback beta rejected; retrying without server-side fallbacks")
                self._fallbacks = False
                return await self.structured(
                    system=system, messages=messages, schema=schema, max_tokens=max_tokens
                )
            raise LLMUnavailableError(f"LLM request rejected: {exc.message}") from exc
        except anthropic.AuthenticationError as exc:
            raise LLMUnavailableError("LLM credentials were rejected") from exc
        except anthropic.RateLimitError as exc:
            raise LLMUnavailableError("LLM rate limit reached") from exc
        except anthropic.APIStatusError as exc:
            raise LLMUnavailableError(f"LLM service error ({exc.status_code})") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMUnavailableError("Could not reach the LLM service") from exc

        if response.stop_reason == "refusal":
            raise LLMRefusalError("The model declined this request")
        parsed = response.parsed_output
        if parsed is None:
            raise LLMUnavailableError(f"LLM returned no structured output ({response.stop_reason})")
        return LLMResult(
            value=parsed,
            provider=self.name,
            model=response.model,
            latency_ms=int((time.perf_counter() - started) * 1000),
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            meta={"request_id": getattr(response, "_request_id", None)},
        )

    async def stream_text(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]:
        anthropic = self._anthropic
        try:
            async with self._client.beta.messages.stream(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,  # type: ignore[arg-type]
                output_config={"effort": "low"},
                **self._extra(),
            ) as stream:
                async for text in stream.text_stream:
                    yield text
                final = await stream.get_final_message()
                if final.stop_reason == "refusal":
                    raise LLMRefusalError("The model declined this request")
        except anthropic.APIStatusError as exc:
            raise LLMUnavailableError(f"LLM service error ({exc.status_code})") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMUnavailableError("Could not reach the LLM service") from exc


_provider: LLMProvider | None = None


def get_llm() -> LLMProvider:
    global _provider
    if _provider is None:
        settings = get_settings()
        provider: LLMProvider = AnthropicProvider() if settings.llm_configured else OfflineProvider()  # type: ignore[assignment]
        _provider = provider
    return _provider


def set_llm(provider: LLMProvider | None) -> None:
    """Override the provider (tests, or after configuration changes)."""
    global _provider
    _provider = provider
