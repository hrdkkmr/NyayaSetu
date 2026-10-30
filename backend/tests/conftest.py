"""Test configuration.

Tests run against a temporary SQLite database with the real official legal sources
ingested once per session. Fixtures here are synthetic and exist only inside tests.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="nyayasetu-tests-"))
os.environ.update({
    "ENVIRONMENT": "test",
    "DATABASE_URL": f"sqlite+aiosqlite:///{(_TMP / 'test.db').as_posix()}",
    "SECRET_KEY": "test-secret-key-that-is-long-enough-123",
    "LOCAL_STORAGE_PATH": str(_TMP / "storage"),
    "LLM_PROVIDER": "offline",
    "ANTHROPIC_API_KEY": "",
    "SARVAM_API_KEY": "",
    "REDIS_URL": "",
    "SMTP_HOST": "",
    "EXPOSE_DEV_RESET_TOKENS": "true",
    "AUTH_RATE_LIMIT_PER_MINUTE": "1000",
    "RATE_LIMIT_PER_MINUTE": "10000",
    "CORS_ORIGINS": "http://localhost:3000",
    "OCR_PROVIDER": "none",
})

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

from app.agents.llm import set_llm  # noqa: E402
from app.core.ratelimit import limiter  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_engine, session_scope  # noqa: E402
from app.legal.ingestion import ingest_all  # noqa: E402
from app.main import app  # noqa: E402


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def database() -> AsyncIterator[None]:
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_scope() as db:
        await ingest_all(db, fetch_live=False)
    yield


@pytest.fixture(autouse=True)
def _reset_state() -> None:
    limiter.reset()
    set_llm(None)


@pytest_asyncio.fixture(loop_scope="session")
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


class Session:
    """A signed-in browser-like client that sends the CSRF header automatically."""

    def __init__(self, client: httpx.AsyncClient, user: dict) -> None:
        self.client = client
        self.user = user

    def _headers(self) -> dict[str, str]:
        return {"X-CSRF-Token": self.client.cookies.get("ns_csrf") or ""}

    async def get(self, url: str, **kw):  # type: ignore[no-untyped-def]
        return await self.client.get(f"/api/v1{url}", **kw)

    async def post(self, url: str, **kw):  # type: ignore[no-untyped-def]
        return await self.client.post(f"/api/v1{url}", headers=self._headers(), **kw)

    async def put(self, url: str, **kw):  # type: ignore[no-untyped-def]
        return await self.client.put(f"/api/v1{url}", headers=self._headers(), **kw)

    async def patch(self, url: str, **kw):  # type: ignore[no-untyped-def]
        return await self.client.patch(f"/api/v1{url}", headers=self._headers(), **kw)

    async def delete(self, url: str, **kw):  # type: ignore[no-untyped-def]
        return await self.client.delete(f"/api/v1{url}", headers=self._headers(), **kw)


_counter = {"n": 0}


async def register(client: httpx.AsyncClient, *, consents: bool = True, language: str = "en") -> Session:
    _counter["n"] += 1
    email = f"user{_counter['n']}-{os.getpid()}@example.com"
    resp = await client.post("/api/v1/auth/register", json={
        "email": email, "full_name": "Test Citizen", "password": "correct-horse-42", "language": language,
        "accept_terms": True,
    })
    assert resp.status_code == 201, resp.text
    session = Session(client, resp.json()["user"])
    if consents:
        r = await session.patch("/users/me/preferences", json={
            "consent_store_transcripts": True, "consent_document_storage": True})
        assert r.status_code == 200, r.text
    return session


@pytest_asyncio.fixture(loop_scope="session")
async def citizen(client: httpx.AsyncClient) -> Session:
    return await register(client)


async def make_admin(email: str) -> None:
    from sqlalchemy import update

    from app.models import User

    async with session_scope() as db:
        await db.execute(update(User).where(User.email == email).values(role="admin"))
