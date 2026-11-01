from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from app.agents.llm import LLMRefusalError, LLMUnavailableError, OpenAICompatibleProvider
from app.config import Settings


class Echo(BaseModel):
    summary: str
    confidence: float


def _provider(handler: Callable[[httpx.Request], httpx.Response]) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        "https://llm.example.test/v1", "test-key", "test-model", transport=httpx.MockTransport(handler)
    )


def _completion(content: str, finish_reason: str = "stop", **message: Any) -> httpx.Response:
    return httpx.Response(200, json={
        "id": "cmpl-1", "model": "test-model",
        "choices": [{"message": {"role": "assistant", "content": content, **message},
                     "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7},
    })


async def _structured(provider: OpenAICompatibleProvider) -> Echo:
    result = await provider.structured(system="sys", messages=[{"role": "user", "content": "hi"}], schema=Echo)
    return result.value


async def test_structured_output_uses_json_schema_and_validates() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-key"
        seen.append(json.loads(request.content))
        return _completion('{"summary": "ok", "confidence": 0.5}')

    provider = _provider(handler)
    result = await provider.structured(system="sys", messages=[{"role": "user", "content": "hi"}], schema=Echo)
    assert result.value == Echo(summary="ok", confidence=0.5)
    assert (result.provider, result.input_tokens, result.output_tokens) == ("openai_compatible", 11, 7)
    body = seen[0]
    assert body["response_format"]["type"] == "json_schema"
    assert body["messages"][0] == {"role": "system", "content": "sys"}


async def test_json_schema_rejection_falls_back_to_json_mode() -> None:
    formats: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        formats.append(body["response_format"]["type"])
        if body["response_format"]["type"] == "json_schema":
            return httpx.Response(400, json={"error": {"message": "response_format not supported"}})
        assert "JSON schema" in body["messages"][0]["content"]
        return _completion('```json\n{"summary": "ok", "confidence": 1}\n```')

    provider = _provider(handler)
    assert (await _structured(provider)).summary == "ok"
    assert (await _structured(provider)).summary == "ok"
    assert formats == ["json_schema", "json_object", "json_object"]


@pytest.mark.parametrize(("status", "message"), [(401, "credentials"), (429, "rate limit"), (503, "503")])
async def test_http_errors_become_unavailable(status: int, message: str) -> None:
    provider = _provider(lambda _req: httpx.Response(status, json={}))
    with pytest.raises(LLMUnavailableError, match=message):
        await _structured(provider)


async def test_invalid_json_is_unavailable_not_trusted() -> None:
    provider = _provider(lambda _req: _completion('{"summary": "missing confidence"}'))
    with pytest.raises(LLMUnavailableError):
        await _structured(provider)


async def test_refusal_is_reported() -> None:
    provider = _provider(lambda _req: _completion("", refusal="no"))
    with pytest.raises(LLMRefusalError):
        await _structured(provider)


async def test_connection_failure_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    with pytest.raises(LLMUnavailableError, match="reach"):
        await _structured(_provider(handler))


async def test_stream_text_parses_server_sent_events() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["stream"] is True
        chunks = [{"choices": [{"delta": {"content": part}}]} for part in ("Nam", "aste")]
        sse = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})

    parts = [p async for p in _provider(handler).stream_text(system="s", messages=[])]
    assert "".join(parts) == "Namaste"


def test_settings_require_base_key_and_model() -> None:
    base = {"llm_provider": "openai_compatible", "llm_api_base": "https://llm.example.test/v1",
            "llm_api_key": "k", "llm_model": "m"}
    assert Settings(**base).llm_configured
    assert not Settings(**{**base, "llm_model": None}).llm_configured
    assert not Settings(**{**base, "llm_api_key": None}).llm_configured


@pytest.mark.parametrize("url", ["postgres://u:p@db:5432/n", "postgresql://u:p@db:5432/n",
                                 "postgresql+asyncpg://u:p@db:5432/n"])
def test_database_url_uses_asyncpg_driver(url: str) -> None:
    assert Settings(database_url=url).database_url == "postgresql+asyncpg://u:p@db:5432/n"
