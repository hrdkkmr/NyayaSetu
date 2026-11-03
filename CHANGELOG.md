# Changelog

## Unreleased

### Added
- Statutory deadline calculator additions: s.36(2) admissibility target on reported filing;
  user-set legal-notice deadline (labelled non-statutory); `.ics` export and Google Calendar links.
- Live agent telemetry: `trace` and `ai_status` in turn responses (text and voice), `GET
  /cases/{id}/agent-trace` with provenance re-read from the knowledge base, and a collapsible drawer.
- Backup LLM model (`LLM_FALLBACK_MODEL`) and an AI/rules status badge.
- AI evidence extraction from uploads (brand, product, defect summary and more), quote-checked and
  reviewed by the user before use.
- e-Jagriti local co-pilot bundle (`GET /filing/{id}/copilot-bundle`).

### Fixed
- Transliterated names (e.g. "राहुल" read as "Rahil") were stored as user-stated; names must now
  appear verbatim or are treated as inferences needing confirmation.
- The AI consent text no longer names a specific vendor.
- `LLM_PROVIDER=openai_compatible` (`LLM_API_BASE`, `LLM_API_KEY`, `LLM_MODEL`): agents can use any
  OpenAI-style Chat Completions API (xAI Grok, Groq) with the same consent gate and rule fallback.
- Password reset by 6-digit email code (one page: request → enter code + new password), with a
  bilingual HTML email; codes expire in 10 minutes and are burned after 5 wrong attempts.
  `/reset-password` links now redirect to `/forgot-password`.
- Sign in with Google (`GOOGLE_CLIENT_ID`; `GET /auth/providers`, `POST /auth/google`); the button is
  hidden when not configured. Migration `0002` adds `users.google_sub` and
  `password_reset_tokens.attempts`.
- `render.yaml` Blueprint (free Postgres + Docker API, Groq LLM); `DATABASE_URL` values starting
  `postgres://`/`postgresql://` are converted to the asyncpg driver automatically.
- `.env.example` reorganised for a Render (API) + Vercel (web) deployment with Gmail SMTP;
  Render + Vercel steps in `docs/DEPLOYMENT_GUIDE.md`.

### Changed
- `POST /auth/password/reset` takes `{email, code, new_password}` instead of `{token, new_password}`;
  dev responses expose `dev_reset_code` instead of `dev_reset_token`.
- Agent execution rows record the active provider's name instead of always `anthropic`.

## 0.1.0 — 2026-10-31 (first implementation)

### Added
- FastAPI backend (30-table schema, Alembic migration) with auth (argon2, JWT + rotating refresh,
  CSRF, bearer for native clients), cases, provenance-tracked facts, deadlines, updates, audit.
- Legal knowledge base from official sources: Consumer Protection Act 2019 (Gazette), Jurisdiction
  Rules 2021 (G.S.R. 912(E)), CDRC Amendment Rules 2023 (G.S.R. 606(E)); section-aware chunking,
  hybrid retrieval, Hindi query expansion, version/amendment metadata.
- LangGraph case workflow: safety, intake, classification, research, planning, documents,
  verification, filing, tracking; persistent checkpoints, retries, approval interrupts.
- Deterministic consumer rules (forum, fee, limitation, territory, consumer status, reliefs, appeal).
- Document engine: secure uploads (validation, encryption, extraction, injection flags), drafts,
  versioning, verification, PDF/DOCX, hash-bound approvals.
- e-Jagriti guided filing, optional Playwright assist, user-reported acknowledgements, reviewer
  verification.
- Voice: ticketed WebSocket, Sarvam STT/TTS adapters, browser speech, VAD, barge-in, reconnection.
- Next.js frontend in Hindi and English: landing, auth, dashboard, case workspace, document review,
  research, settings, admin.
- Tests (backend pytest, Vitest, Playwright), Docker, compose, CI, docs, Claude Code skills/agents.

### Security (from the internal review)
- Client IP no longer taken from `X-Forwarded-For`; per-account login/reset rate limits.
- Refresh-token reuse revokes all sessions; atomic rotation; all reset links consumed on reset;
  reset email sent after the response.
- Voice: single-use tickets, session/user re-checked per turn, per-turn rate limit, idle and
  maximum-duration timeouts; stored recordings tracked and deleted on consent withdrawal or
  account deletion.
- Upload size enforced while reading; explicit image pixel limit.
- Sentry: no local variables, request bodies or breadcrumbs.
- Post-login redirect restricted to same-origin paths.
- Filing verification only from user-reported submissions; verified filings cannot be edited.

### Fixed
- SQLite deadlock under concurrent writes (`BEGIN IMMEDIATE`), found by the E2E suite.
- Hindi yes/no/skip detection (`\b` does not work after Devanagari combining marks).
