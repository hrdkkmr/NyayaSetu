"""Test doubles. Only used inside the automated test suite."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from pydantic import BaseModel

from app.agents.llm import LLMResult, LLMUnavailableError


class ScriptedProvider:
    """An LLM provider that returns scripted structured outputs keyed by schema class name."""

    name = "scripted"
    model = "scripted-test-model"

    def __init__(self, responses: dict[str, Callable[[str], BaseModel] | BaseModel | Exception]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    @property
    def available(self) -> bool:
        return True

    async def structured(self, *, system: str, messages: list[dict[str, Any]], schema: type[BaseModel],
                         max_tokens: int = 4096) -> LLMResult[Any]:
        prompt = messages[-1]["content"]
        self.calls.append({"schema": schema.__name__, "system": system, "prompt": prompt})
        response = self.responses.get(schema.__name__)
        if response is None:
            raise LLMUnavailableError(f"no scripted response for {schema.__name__}")
        if isinstance(response, Exception):
            raise response
        value = response(prompt) if callable(response) and not isinstance(response, BaseModel) else response
        return LLMResult(value=value, provider=self.name, model=self.model, latency_ms=1)

    async def stream_text(self, **_: Any) -> AsyncIterator[str]:
        yield "scripted"
