# Security and Privacy

NyayaSetu handles highly sensitive legal and personal information. Controls below are implemented
unless marked otherwise.

## Authentication & sessions
- Passwords: argon2 (rehash on login when parameters change); ≥10 chars with letters + digits.
- Access JWT (HS256, 15 min, bound to a session id) + opaque refresh token (HMAC-hashed at rest,
  rotated on every use, 14 days). Logout and password reset revoke sessions.
- Web: httpOnly `SameSite=Lax` cookies (`Secure` in production) + CSRF double-submit header.
  Native clients: bearer tokens, CSRF-exempt.
- Login timing equalised for unknown emails; password reset responses do not reveal accounts.
- Rate limits: auth endpoints per IP **and per account** (default 10/min), authenticated users per user
  (120/min), per voice turn; Redis-backed when configured. Client IP comes from the connection;
  `X-Forwarded-For` is honoured only for proxies in `FORWARDED_ALLOW_IPS` (uvicorn `--proxy-headers`).
- Refresh-token reuse revokes every session of the account; rotation is atomic. Password reset uses a
  6-digit email code (10 min): only the newest code is valid, it is stored as an HMAC bound to its
  record, and it is burned after 5 wrong attempts (plus per-IP and per-account rate limits). Reset
  emails are sent after the response (no timing signal).
- Google sign-in: the Google ID token's signature (Google's published keys), audience
  (`GOOGLE_CLIENT_ID`), issuer, expiry and `email_verified` are checked server-side. The Google
  `sub` is stored on the user. Linking Google to an existing account with the same email replaces
  that account's password and revokes its sessions, because registration does not verify email.
- Voice: single-use 60 s tickets (in-process registry), auth session re-checked on connect and every
  turn, 5-minute idle and 2-hour maximum session.

## Authorisation
- Roles: citizen, legal_reviewer, admin. Admin routes use `require_roles`.
- Ownership: every case-scoped resource is loaded through the owning case; other users get 404.
- Consequential actions (approvals, filing authorisation, acknowledgements, verification) are
  explicit API calls with statements recorded in `approvals` and the audit log.

## Data protection
- Uploads encrypted with AES-256-GCM (`STORAGE_ENCRYPTION_KEY`, 32 bytes; derived from
  `SECRET_KEY` only for development); S3 server-side encryption also requested. Storage keys never
  leave the server; downloads are audited and `no-store`.
- In transit: HTTPS at the edge; HSTS when `COOKIE_SECURE=true`; WebSocket over WSS in production.
- Security headers on API and web (nosniff, frame deny, referrer policy, permissions policy).
- Production start blocked if SECRET_KEY/COOKIE_SECURE/DB/CORS/dev-token settings are unsafe.

## Untrusted content & prompt injection
- Uploaded files are validated by content (size enforced while streaming); active PDFs, macro
  documents, zip bombs and images over 40 MP are rejected.
- Extracted text is data: injection phrases are detected and flagged to the user; extracted fields
  become facts only after user acceptance; agents cannot create approvals or change roles; LLM input
  from documents is wrapped (`wrap_untrusted`).
- LLM outputs are validated (excerpt check, citation check, guarantee check).

## Logging & audit
- JSON logs with redaction of keys, tokens, passwords and JWTs; httpx URL logging suppressed.
- Audit log of auth events, consent changes, uploads/downloads, fact edits, draft edits, approvals,
  filing events, admin actions. Metadata is scrubbed of text/content/secrets.
- Sentry with `send_default_pii=False`, `include_local_variables=False`, no request bodies, and a
  `before_send` hook that strips frame variables and breadcrumbs.

## Consent (all off by default except as chosen at registration)
| Consent | Effect when off |
|---|---|
| Store transcripts | Messages stored as placeholders; facts still saved as the case record |
| Store documents | Uploads refused |
| Keep voice recordings | Audio transcribed and discarded; turning it off deletes stored recordings |
| External AI processing | No LLM (Groq/Claude) is called for that user, neither for conversation nor for reading their uploads; rule-based agents and pattern extraction only |
Speech via Sarvam is used only if the user selects it in Settings.

## Retention & deletion
- Users can export their data (`GET /users/me/export`).
- Deletion request → admin executes within 30 days (`/admin/deletion-requests/{id}/execute`):
  deletes encrypted files and the user row (cascades to cases, facts, messages, documents,
  sessions). Audit entries retain no content.
- Transcripts, documents and recordings are kept until the user deletes them or the account.
  *Automatic time-based purging is not yet implemented.*

## Indian data protection
Controls are designed with the Digital Personal Data Protection Act, 2023 in mind (notice,
purpose-specific consent, withdrawal, access/export, erasure). A formal legal compliance review,
grievance-officer details and data-processing agreements with Anthropic/Sarvam are required before
production use and are outside this codebase.

## Accepted risks
Registration tells a user when an email is already registered (usability); rate limits apply.
Single-use voice tickets are tracked per API process; across several instances replay is bounded
by the 60 s ticket lifetime (move to Redis when scaling out). The PDF active-content check is a
byte-pattern scan (hex-escaped names are not decoded); downloads are served as attachments with
`nosniff`.

## Not yet implemented
Antivirus scanning of uploads; Postgres row-level security; MFA; automated retention purge;
penetration test.
