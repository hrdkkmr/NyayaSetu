"""Verification of Google Identity Services ID tokens ("Sign in with Google").

The browser obtains a signed ID token (JWT) from Google and posts it to
`/auth/google`. It is accepted only if Google's published keys verify the signature,
the audience is our `GOOGLE_CLIENT_ID`, the issuer is Google and the email is verified.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import jwt

from app.config import get_settings
from app.core.errors import AuthError, IntegrationUnavailableError

GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = frozenset({"accounts.google.com", "https://accounts.google.com"})

_jwks = jwt.PyJWKClient(GOOGLE_CERTS_URL, cache_keys=True, lifespan=3600, timeout=10)


@dataclass(frozen=True)
class GoogleIdentity:
    sub: str
    email: str
    name: str | None


def google_configured() -> bool:
    return bool(get_settings().google_client_id)


def _verify_sync(credential: str, client_id: str) -> dict[str, Any]:
    try:
        key = _jwks.get_signing_key_from_jwt(credential).key
    except jwt.PyJWKClientConnectionError as exc:
        raise IntegrationUnavailableError("Could not reach Google to verify sign-in. Please try again.",
                                          code="google_unreachable") from exc
    except jwt.PyJWTError as exc:
        raise AuthError("Google sign-in could not be verified.", code="google_invalid") from exc
    try:
        claims: dict[str, Any] = jwt.decode(
            credential, key, algorithms=["RS256"], audience=client_id,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise AuthError("Google sign-in could not be verified.", code="google_invalid") from exc
    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise AuthError("Google sign-in could not be verified.", code="google_invalid")
    return claims


async def verify_google_credential(credential: str) -> GoogleIdentity:
    client_id = get_settings().google_client_id
    if not client_id:
        raise IntegrationUnavailableError("Google sign-in is not configured.", code="google_not_configured")
    claims = await asyncio.to_thread(_verify_sync, credential, client_id)
    email = claims.get("email")
    # Google sends email_verified as a boolean (older tokens used the string "true").
    if not email or claims.get("email_verified") not in (True, "true"):
        raise AuthError("Your Google account email is not verified.", code="google_email_unverified")
    name = claims.get("name")
    return GoogleIdentity(sub=str(claims["sub"]), email=str(email).lower(),
                          name=str(name).strip() if name else None)
