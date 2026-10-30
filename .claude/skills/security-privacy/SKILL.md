---
name: security-privacy
description: Use for any change to auth, sessions, permissions, uploads, storage, logging, consent, data export/deletion, CORS, or before a release security review.
---

# Security & privacy

## Objective
Protect highly sensitive legal and personal data; make consent meaningful; keep every consequential
action attributable.

## When to use
`core/*`, `api/auth.py`, `api/users.py`, uploads/storage, logging, settings, CORS, voice auth.

## Controls in place (keep them working)
- Passwords: argon2. Access JWT (15 min) + rotating opaque refresh tokens (hashed, single-use).
- Browser: httpOnly cookies + CSRF double-submit (`X-CSRF-Token`); native clients use bearer tokens.
- Ownership: `get_owned_case` → 404 for other users' resources. Admin routes: `require_roles`.
- Rate limits (Redis or memory), security headers, strict CORS, production config guard
  (`Settings.validate_for_production`).
- Storage: AES-256-GCM app-level encryption, random keys, no raw URLs, downloads audited.
- Logs: JSON + redaction of keys/tokens/passwords; audit `meta` scrubbed of text/content.
- Consent flags gate transcripts, audio, documents and external AI.
- Prompt-injection: untrusted text wrapped and flagged; agents cannot change permissions or approvals.

## Rules
- Never log request bodies, document text, transcripts, tokens or keys.
- New endpoints: authenticate, check ownership, validate input with Pydantic, audit if consequential.
- Never weaken CSRF or ownership checks for convenience; add tests instead.
- Data retention/deletion policy is in `docs/SECURITY_AND_PRIVACY.md` — update it when you store new data.

## Testing expectations
Cross-user access tests for every new resource, CSRF test for cookie mutations, token tamper test,
malicious upload tests, injection tests, encryption tamper test.

## Common failure scenarios
- Returning ORM objects directly (leaks `storage_key`, hashes) — use `api/serializers.py`.
- Trusting `X-Forwarded-For` without a trusted proxy (configure the platform proxy).
- `EXPOSE_DEV_RESET_TOKENS` left on outside development (production guard blocks start).
