"""LLM provider abstraction.

Agents depend on `LLMProvider`, never on a vendor SDK directly. Three providers ship:

* `AnthropicProvider` - Claude via the official Anthropic SDK (structured outputs
  validated against Pydantic models, streaming text, server-side refusal fallbacks).
* `OpenAICompatibleProvider` - any OpenAI-style Chat Completions API (xAI Grok, Groq, ...)
  over httpx. Structured output uses `response_format` JSON schema, falling back to JSON
  mode; replies are always validated against the Pydantic model.
* `OfflineProvider` - reports itself unavailable. Agents then use their
  deterministic rule-based paths, so the product keeps working without credentials
  and never pretends an LLM produced an answer.

Tests inject a `ScriptedProvider` (see tests/fakes.py).
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Generic, Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMUnavailableError(RuntimeError):
    """No LLM is configured, or the provider failed after retries."""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        # False when another model on the same account cannot help (e.g. rejected credentials).
        self.retryable = retryable


# Per-request log of LLM calls, so a workflow run can report honestly whether AI, a backup
# model or the rule path produced its answer. Context variables are safe across concurrent requests.
_call_log: ContextVar[list[dict[str, Any]] | None] = ContextVar("llm_call_log", default=None)


@contextmanager
def track_llm_calls() -> Iterator[list[dict[str, Any]]]:
    log: list[dict[str, Any]] = []
    token = _call_log.set(log)
    try:
        yield log
    finally:
        _call_log.reset(token)


def log_llm_call(model: str | None, ok: bool, *, backup: bool = False, error: str | None = None) -> None:
    log = _call_log.get()
    if log is not None:
        log.append({"model": model, "ok": ok, "backup": backup, "error": error})


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
        try:
            result = await self._structured(system=system, messages=messages, schema=schema, max_tokens=max_tokens)
        except LLMUnavailableError as exc:
            log_llm_call(self.model, False, error=str(exc))
            raise
        log_llm_call(self.model, True)
        return result

    async def _structured(
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
                return await self._structured(
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


class OpenAICompatibleProvider:
    """Chat Completions over plain HTTP; works with xAI Grok, Groq and other compatible APIs."""

    name = "openai_compatible"

    def __init__(
        self,
        base: str,
        api_key: str,
        model: str,
        timeout: float = 90.0,
        transport: httpx.AsyncBaseTransport | None = None,
        fallback_model: str | None = None,
    ) -> None:
        self.model: str | None = model
        # Tried once when the primary model is rate-limited, down or returns unusable output.
        self.fallback_model = fallback_model if fallback_model and fallback_model != model else None
        self._url = f"{base.rstrip('/')}/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._timeout = timeout
        self._transport = transport
        # Some compatible APIs/models reject `json_schema`; after one rejection use JSON mode.
        self._json_mode_only = False

    @property
    def available(self) -> bool:
        return True

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self._timeout, headers=self._headers, transport=self._transport)

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
        if resp.status_code in (401, 403):
            raise LLMUnavailableError("LLM credentials were rejected", retryable=False)
        if resp.status_code == 429:
            raise LLMUnavailableError("LLM rate limit reached")
        if resp.status_code >= 400:
            raise LLMUnavailableError(f"LLM service error ({resp.status_code})")

    def _body(
        self, system: str, messages: list[dict[str, Any]], max_tokens: int, schema: type[BaseModel] | None,
        model: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"model": model or self.model, "max_tokens": max_tokens}
        if schema is not None:
            schema_json = schema.model_json_schema()
            if self._json_mode_only:
                system = (f"{system}\n\nReply with a single JSON object (no prose, no code fences) that "
                          f"matches this JSON schema:\n{json.dumps(schema_json)}")
                body["response_format"] = {"type": "json_object"}
            else:
                body["response_format"] = {"type": "json_schema",
                                           "json_schema": {"name": schema.__name__, "schema": schema_json}}
        body["messages"] = [{"role": "system", "content": system}, *messages]
        return body

    async def structured(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        schema: type[T],
        max_tokens: int = 4096,
    ) -> LLMResult[T]:
        try:
            result = await self._structured_once(self.model, system, messages, schema, max_tokens)
        except LLMUnavailableError as exc:
            log_llm_call(self.model, False, error=str(exc))
            if not (exc.retryable and self.fallback_model):
                raise
            logger.warning("Primary LLM failed (%s); trying backup model", exc)
            try:
                result = await self._structured_once(self.fallback_model, system, messages, schema, max_tokens)
            except LLMUnavailableError as backup_exc:
                log_llm_call(self.fallback_model, False, backup=True, error=str(backup_exc))
                raise
            log_llm_call(self.fallback_model, True, backup=True)
            result.meta["backup_model"] = True
            return result
        log_llm_call(self.model, True)
        return result

    async def _structured_once(
        self, model: str | None, system: str, messages: list[dict[str, Any]], schema: type[T], max_tokens: int,
    ) -> LLMResult[T]:
        started = time.perf_counter()
        try:
            async with self._client() as client:
                resp = await client.post(self._url, json=self._body(system, messages, max_tokens, schema, model))
        except httpx.HTTPError as exc:
            raise LLMUnavailableError("Could not reach the LLM service") from exc
        if resp.status_code == 400 and not self._json_mode_only:
            logger.warning("JSON schema output rejected; retrying with JSON mode")
            self._json_mode_only = True
            return await self._structured_once(model, system, messages, schema, max_tokens)
        self._raise_for_status(resp)

        try:
            data = resp.json()
            choice = data["choices"][0]
            message = choice["message"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMUnavailableError("LLM returned an unexpected response") from exc
        if message.get("refusal") or choice.get("finish_reason") == "content_filter":
            raise LLMRefusalError("The model declined this request")
        content = (message.get("content") or "").strip()
        if content.startswith("```"):
            content = content.strip("`").removeprefix("json").strip()
        try:
            parsed = schema.model_validate_json(content)
        except ValidationError as exc:
            raise LLMUnavailableError(
                f"LLM returned no valid structured output ({choice.get('finish_reason')})"
            ) from exc
        usage = data.get("usage") or {}
        return LLMResult(
            value=parsed,
            provider=self.name,
            model=data.get("model", model),
            latency_ms=int((time.perf_counter() - started) * 1000),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            meta={"request_id": data.get("id")},
        )

    async def stream_text(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]:
        body = {**self._body(system, messages, max_tokens, None), "stream": True}
        try:
            async with self._client() as client, client.stream("POST", self._url, json=body) as resp:
                self._raise_for_status(resp)
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        choice = json.loads(payload)["choices"][0]
                    except (ValueError, KeyError, IndexError):
                        continue
                    if choice.get("finish_reason") == "content_filter":
                        raise LLMRefusalError("The model declined this request")
                    text = (choice.get("delta") or {}).get("content")
                    if text:
                        yield text
        except httpx.HTTPError as exc:
            raise LLMUnavailableError("Could not reach the LLM service") from exc


_provider: LLMProvider | None = None


def _build_provider() -> LLMProvider:
    settings = get_settings()
    if not settings.llm_configured:
        return OfflineProvider()  # type: ignore[return-value]
    if settings.llm_provider == "openai_compatible":
        assert settings.llm_api_base and settings.llm_api_key and settings.llm_model
        return OpenAICompatibleProvider(  # type: ignore[return-value]
            settings.llm_api_base, settings.llm_api_key, settings.llm_model, settings.llm_timeout_seconds,
            fallback_model=settings.llm_fallback_model,
        )
    return AnthropicProvider()  # type: ignore[return-value]


def get_llm() -> LLMProvider:
    global _provider
    if _provider is None:
        _provider = _build_provider()
    return _provider


def set_llm(provider: LLMProvider | None) -> None:
    """Override the provider (tests, or after configuration changes)."""
    global _provider
    _provider = provider
