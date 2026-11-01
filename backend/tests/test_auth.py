from __future__ import annotations

import httpx

from tests.conftest import register


async def test_register_login_me_logout(client: httpx.AsyncClient) -> None:
    s = await register(client)
    me = await s.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == s.user["email"]
    assert "password_hash" not in me.text
    assert (await s.post("/auth/logout")).status_code == 200
    client.cookies.clear()
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    login = await client.post("/api/v1/auth/login", json={"email": s.user["email"], "password": "correct-horse-42"})
    assert login.status_code == 200


async def test_wrong_password_and_unknown_email_look_the_same(client: httpx.AsyncClient) -> None:
    s = await register(client)
    client.cookies.clear()
    bad = await client.post("/api/v1/auth/login", json={"email": s.user["email"], "password": "nope-nope-12"})
    unknown = await client.post("/api/v1/auth/login", json={"email": "ghost@example.com", "password": "nope-nope-12"})
    assert bad.status_code == unknown.status_code == 401
    assert bad.json()["error"]["code"] == unknown.json()["error"]["code"] == "invalid_credentials"


async def test_duplicate_and_weak_registration_rejected(client: httpx.AsyncClient) -> None:
    s = await register(client)
    dup = await client.post("/api/v1/auth/register", json={"email": s.user["email"], "full_name": "X Y",
                                                           "password": "correct-horse-42", "accept_terms": True})
    assert dup.status_code == 409
    weak = await client.post("/api/v1/auth/register", json={"email": "weak@example.com", "full_name": "X Y",
                                                            "password": "short", "accept_terms": True})
    assert weak.status_code == 422
    no_terms = await client.post("/api/v1/auth/register", json={"email": "t@example.com", "full_name": "X Y",
                                                                "password": "correct-horse-42", "accept_terms": False})
    assert no_terms.status_code == 422


async def test_csrf_required_for_cookie_mutations(client: httpx.AsyncClient) -> None:
    await register(client)
    resp = await client.post("/api/v1/cases", json={"language": "en"})  # no CSRF header
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "csrf_failed"


async def test_bearer_tokens_for_native_clients(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/v1/auth/register", headers={"X-Client-Type": "mobile"}, json={
        "email": "mobile@example.com", "full_name": "Mobile User", "password": "correct-horse-42",
        "accept_terms": True})
    tokens = resp.json()
    assert tokens["access_token"] and tokens["refresh_token"]
    client.cookies.clear()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    created = await client.post("/api/v1/cases", json={"language": "hi"}, headers=headers)
    assert created.status_code == 201  # bearer auth is exempt from CSRF


async def test_refresh_rotation_invalidates_old_token(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/v1/auth/register", headers={"X-Client-Type": "mobile"}, json={
        "email": "rotate@example.com", "full_name": "Rotate User", "password": "correct-horse-42",
        "accept_terms": True})
    old = resp.json()["refresh_token"]
    client.cookies.clear()
    first = await client.post("/api/v1/auth/refresh", json={"refresh_token": old}, headers={"X-Client-Type": "mobile"})
    assert first.status_code == 200
    reused = await client.post("/api/v1/auth/refresh", json={"refresh_token": old})
    assert reused.status_code == 401


async def test_password_reset_flow_revokes_sessions(client: httpx.AsyncClient) -> None:
    s = await register(client)
    email = s.user["email"]
    forgot = await client.post("/api/v1/auth/password/forgot", json={"email": email})
    code = forgot.json()["dev_reset_code"]
    assert len(code) == 6 and code.isdigit()
    reset = await client.post("/api/v1/auth/password/reset",
                              json={"email": email, "code": code, "new_password": "brand-new-pass-77"})
    assert reset.status_code == 200
    assert (await client.get("/api/v1/auth/me")).status_code == 401  # old session revoked
    reuse = await client.post("/api/v1/auth/password/reset",
                              json={"email": email, "code": code, "new_password": "another-pass-88"})
    assert reuse.status_code == 400
    login = await client.post("/api/v1/auth/login", json={"email": s.user["email"], "password": "brand-new-pass-77"})
    assert login.status_code == 200


async def test_forgot_password_does_not_reveal_accounts(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/v1/auth/password/forgot", json={"email": "nobody@example.com"})
    assert resp.status_code == 200
    assert "dev_reset_code" not in resp.json()


async def test_auth_rate_limit(client: httpx.AsyncClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "auth_rate_limit_per_minute", 3)
    codes = [(await client.post("/api/v1/auth/login", json={"email": "x@example.com", "password": "aaaaaaaaaa1"})).status_code
             for _ in range(5)]
    assert 429 in codes


async def test_session_listing_and_revocation(client: httpx.AsyncClient) -> None:
    s = await register(client)
    sessions = (await s.get("/users/me/sessions")).json()
    assert len(sessions) == 1 and sessions[0]["current"] is True
