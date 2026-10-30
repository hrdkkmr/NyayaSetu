"""Embedding providers.

* `HashingEmbedder` (default) - deterministic signed feature hashing of stemmed
  unigrams and bigrams. Works offline and is reproducible, but it captures lexical
  overlap rather than deep semantics. It is labelled as such everywhere it is reported.
* `OpenAICompatibleEmbedder` - any `/embeddings` endpoint that follows the common
  JSON shape (self-hosted models, or a hosted embedding API). Configure with
  EMBEDDING_API_BASE / EMBEDDING_API_KEY / EMBEDDING_MODEL.

Changing provider or dimensions requires re-running ingestion (`python -m app.cli ingest --reembed`).
"""

from __future__ import annotations

import hashlib
import math
from typing import Protocol

import httpx

from app.config import get_settings
from app.legal.text import tokenize


class Embedder(Protocol):
    name: str
    dimensions: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashingEmbedder:
    name = "hashing-v1"

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dimensions
        tokens = tokenize(text)
        features = tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:], strict=False)]
        for feature in features:
            digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "little") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            weight = 1.5 if "_" in feature else 1.0
            vec[index] += sign * weight
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]


class OpenAICompatibleEmbedder:
    def __init__(self, base: str, api_key: str | None, model: str, dimensions: int) -> None:
        self.name = f"api:{model}"
        self.dimensions = dimensions
        self._base = base.rstrip("/")
        self._key = api_key
        self._model = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        headers = {"Authorization": f"Bearer {self._key}"} if self._key else {}
        out: list[list[float]] = []
        async with httpx.AsyncClient(timeout=60) as client:
            for start in range(0, len(texts), 64):
                batch = texts[start : start + 64]
                resp = await client.post(
                    f"{self._base}/embeddings",
                    json={"model": self._model, "input": batch},
                    headers=headers,
                )
                resp.raise_for_status()
                data = sorted(resp.json()["data"], key=lambda d: d["index"])
                for item in data:
                    vector = item["embedding"]
                    if len(vector) != self.dimensions:
                        raise ValueError(
                            f"Embedding has {len(vector)} dimensions; EMBEDDING_DIMENSIONS is "
                            f"{self.dimensions}"
                        )
                    out.append(vector)
        return out


def get_embedder() -> Embedder:
    s = get_settings()
    if s.embedding_provider == "openai_compatible" and s.embedding_api_base and s.embedding_model:
        return OpenAICompatibleEmbedder(
            s.embedding_api_base, s.embedding_api_key, s.embedding_model, s.embedding_dimensions
        )
    return HashingEmbedder(s.embedding_dimensions)


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)
