"""Regression tests for findings from the security review."""

from __future__ import annotations

import io

import httpx
import pytest
from PIL import Image
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app
from tests.conftest import make_admin, register
from tests.test_workflow import LAPTOP_STORY, run_story


async def test_spoofed_forwarded_for_does_not_bypass_auth_limit(client: httpx.AsyncClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "auth_rate_limit_per_minute", 3)
    codes = []
    for i in range(6):
        r = await client.post("/api/v1/auth/login", headers={"X-Forwarded-For": f"10.0.0.{i}"},
                              json={"email": "victim@example.com", "password": "guess-guess-1"})
        codes.append(r.status_code)
    assert 429 in codes


async def test_refresh_token_reuse_revokes_all_sessions(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/v1/auth/register", headers={"X-Client-Type": "mobile"}, json={
        "email": "reuse@example.com", "full_name": "Reuse Test", "password": "correct-horse-42", "accept_terms": True})
    old = resp.json()["refresh_token"]
    client.cookies.clear()
    new = (await client.post("/api/v1/auth/refresh", json={"refresh_token": old},
                             headers={"X-Client-Type": "mobile"})).json()
    client.cookies.clear()
    assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": old})).status_code == 401
    client.cookies.clear()
    # The legitimate (rotated) session was revoked too, because reuse signals theft.
    after = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new['access_token']}"})
    assert after.status_code == 401


async def test_new_reset_code_invalidates_older_codes(client: httpx.AsyncClient) -> None:
    s = await register(client)
    email = s.user["email"]
    first = (await client.post("/api/v1/auth/password/forgot", json={"email": email})).json()["dev_reset_code"]
    second = (await client.post("/api/v1/auth/password/forgot", json={"email": email})).json()["dev_reset_code"]
    if first != second:
        old = await client.post("/api/v1/auth/password/reset",
                                json={"email": email, "code": first, "new_password": "another-pass-88"})
        assert old.status_code == 400
    ok = await client.post("/api/v1/auth/password/reset",
                           json={"email": email, "code": second, "new_password": "brand-new-pass-77"})
    assert ok.status_code == 200
    reuse = await client.post("/api/v1/auth/password/reset",
                              json={"email": email, "code": second, "new_password": "another-pass-88"})
    assert reuse.status_code == 400


async def test_reset_code_is_burned_after_too_many_wrong_attempts(client: httpx.AsyncClient) -> None:
    from app.config import get_settings

    s = await register(client)
    email = s.user["email"]
    code = (await client.post("/api/v1/auth/password/forgot", json={"email": email})).json()["dev_reset_code"]
    wrong = f"{(int(code) + 1) % 1_000_000:06d}"
    for _ in range(get_settings().password_reset_max_attempts):
        r = await client.post("/api/v1/auth/password/reset",
                              json={"email": email, "code": wrong, "new_password": "brand-new-pass-77"})
        assert r.json()["error"]["code"] == "reset_invalid"
    # Even the right code no longer works once the attempt budget is spent.
    r = await client.post("/api/v1/auth/password/reset",
                          json={"email": email, "code": code, "new_password": "brand-new-pass-77"})
    assert r.status_code == 400


async def test_reset_code_cannot_be_used_for_another_account(client: httpx.AsyncClient) -> None:
    victim, attacker = await register(client), await register(client)
    code = (await client.post("/api/v1/auth/password/forgot",
                              json={"email": attacker.user["email"]})).json()["dev_reset_code"]
    r = await client.post("/api/v1/auth/password/reset",
                          json={"email": victim.user["email"], "code": code, "new_password": "brand-new-pass-77"})
    assert r.status_code == 400


async def test_expired_reset_code_is_rejected(client: httpx.AsyncClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.config import get_settings

    s = await register(client)
    monkeypatch.setattr(get_settings(), "password_reset_ttl_minutes", -1)
    code = (await client.post("/api/v1/auth/password/forgot", json={"email": s.user["email"]})).json()["dev_reset_code"]
    r = await client.post("/api/v1/auth/password/reset",
                          json={"email": s.user["email"], "code": code, "new_password": "brand-new-pass-77"})
    assert r.json()["error"]["code"] == "reset_expired"


async def test_voice_ticket_single_use_and_revoked_session(client: httpx.AsyncClient) -> None:
    s = await register(client)
    case = (await s.post("/cases", json={})).json()["case"]
    ticket = (await s.post("/voice/ticket", json={"case_id": case["id"]})).json()["ticket"]
    headers = {"origin": "http://localhost:3000"}
    with TestClient(app) as tc:
        with tc.websocket_connect(f"/api/v1/voice/ws?ticket={ticket}", headers=headers) as ws:
            ws.send_json({"type": "end"})
        with pytest.raises(WebSocketDisconnect), tc.websocket_connect(
                f"/api/v1/voice/ws?ticket={ticket}", headers=headers) as ws:
            ws.receive_json()
    second = (await s.post("/voice/ticket", json={"case_id": case["id"]})).json()["ticket"]
    await s.post("/auth/logout")
    with TestClient(app) as tc, pytest.raises(WebSocketDisconnect), tc.websocket_connect(
            f"/api/v1/voice/ws?ticket={second}", headers=headers) as ws:
        ws.receive_json()


async def test_oversized_image_rejected(client: httpx.AsyncClient) -> None:
    s = await register(client)
    case = (await s.post("/cases", json={})).json()["case"]
    buf = io.BytesIO()
    Image.new("1", (8000, 6000)).save(buf, format="PNG")
    r = await s.post(f"/cases/{case['id']}/uploads", files={"file": ("big.png", buf.getvalue(), "image/png")})
    assert r.json()["error"]["code"] == "image_too_large"


async def test_reviewer_cannot_verify_unsubmitted_filing(client: httpx.AsyncClient) -> None:
    from sqlalchemy import select

    from app.db.session import session_scope
    from app.models import FilingRecord

    s = await register(client)
    case_id, _ = await run_story(s, LAPTOP_STORY)
    async with session_scope() as db:
        record = FilingRecord(case_id=case_id, portal="e_jagriti", mode="guided", status="in_progress")
        db.add(record)
        await db.flush()
        rid = str(record.id)
    await make_admin(s.user["email"])
    r = await s.post(f"/admin/filings/{rid}/verify", json={"official_reference": "portal page"})
    assert r.status_code == 409
    async with session_scope() as db:
        assert (await db.scalar(select(FilingRecord.status).where(FilingRecord.id == record.id))) == "in_progress"
