from __future__ import annotations

import time
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import get_settings
from app.core.errors import AppError, AuthError
from app.services import google_identity
from app.services.email_templates import password_reset_code_email
from app.services.google_identity import GoogleIdentity
from tests.conftest import register

CLIENT_ID = "test-client.apps.googleusercontent.com"
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _SigningKey:
    key = _KEY.public_key()


def _token(**overrides: Any) -> str:
    now = int(time.time())
    claims = {"iss": "https://accounts.google.com", "aud": CLIENT_ID, "sub": "g-123", "iat": now,
              "exp": now + 600, "email": "Citizen@Example.com", "email_verified": True, "name": "Google Citizen"}
    claims.update(overrides)
    return jwt.encode(claims, _KEY, algorithm="RS256", headers={"kid": "k1"})


@pytest.fixture
def google_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "google_client_id", CLIENT_ID)
    monkeypatch.setattr(google_identity._jwks, "get_signing_key_from_jwt", lambda _t: _SigningKey())


async def test_valid_google_token_is_accepted(google_keys: None) -> None:
    identity = await google_identity.verify_google_credential(_token())
    assert identity == GoogleIdentity(sub="g-123", email="citizen@example.com", name="Google Citizen")


@pytest.mark.parametrize("overrides", [
    {"aud": "someone-else.apps.googleusercontent.com"},
    {"iss": "https://evil.example.com"},
    {"exp": int(time.time()) - 60},
])
async def test_tampered_google_tokens_are_rejected(google_keys: None, overrides: dict[str, Any]) -> None:
    with pytest.raises(AuthError):
        await google_identity.verify_google_credential(_token(**overrides))


async def test_token_signed_by_another_key_is_rejected(google_keys: None) -> None:
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode(jwt.decode(_token(), options={"verify_signature": False}), other, algorithm="RS256")
    with pytest.raises(AuthError):
        await google_identity.verify_google_credential(forged)


async def test_unverified_google_email_is_rejected(google_keys: None) -> None:
    with pytest.raises(AuthError, match="not verified"):
        await google_identity.verify_google_credential(_token(email_verified=False))


async def test_google_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "google_client_id", None)
    with pytest.raises(AppError) as exc:
        await google_identity.verify_google_credential(_token())
    assert exc.value.code == "google_not_configured"


async def test_providers_endpoint(client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "google_client_id", None)
    assert (await client.get("/api/v1/auth/providers")).json() == {"google_client_id": None}
    monkeypatch.setattr(get_settings(), "google_client_id", CLIENT_ID)
    assert (await client.get("/api/v1/auth/providers")).json() == {"google_client_id": CLIENT_ID}


async def test_google_sign_in_creates_then_reuses_account(client: httpx.AsyncClient, google_keys: None) -> None:
    token = _token(sub="g-new-1", email="fresh-google@example.com")
    first = await client.post("/api/v1/auth/google", json={"credential": token, "language": "hi"})
    assert first.status_code == 200, first.text
    user = first.json()["user"]
    assert (user["email"], user["full_name"], user["preferences"]["language"]) == (
        "fresh-google@example.com", "Google Citizen", "hi")
    assert (await client.get("/api/v1/auth/me")).status_code == 200
    client.cookies.clear()
    again = await client.post("/api/v1/auth/google", json={"credential": token})
    assert again.json()["user"]["id"] == user["id"]


async def test_google_link_locks_out_preexisting_password_and_sessions(
    client: httpx.AsyncClient, google_keys: None,
) -> None:
    squatter = await register(client)  # registered someone's address without proving ownership
    email = squatter.user["email"]
    client.cookies.clear()
    linked = await client.post("/api/v1/auth/google", json={"credential": _token(sub="g-owner", email=email)})
    assert linked.json()["user"]["id"] == squatter.user["id"]
    client.cookies.clear()
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "correct-horse-42"})
    assert login.status_code == 401


async def test_google_sign_in_rejects_invalid_token(client: httpx.AsyncClient, google_keys: None) -> None:
    resp = await client.post("/api/v1/auth/google", json={"credential": _token(aud="other-client")})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "google_invalid"


def test_reset_email_has_code_in_text_and_html_and_escapes_name() -> None:
    content = password_reset_code_email("<b>Asha</b>", "042913", 10, "en")
    assert "042913" in content.subject and "042913" in content.text
    assert "0 4 2 9 1 3" in content.html
    assert "<b>Asha</b>" not in content.html and "&lt;b&gt;Asha&lt;/b&gt;" in content.html
    assert "10 minutes" in content.text


def test_reset_email_hindi_and_unknown_language_fallback() -> None:
    assert "नमस्ते" in password_reset_code_email("Asha", "123456", 10, "hi").text
    assert "Hello" in password_reset_code_email("Asha", "123456", 10, "ta").text
