# Testing Strategy

## Automated suites (results on 2026-10-30, Windows, Python 3.13, Node 24)
| Suite | Command | Result |
|---|---|---|
| Backend (pytest) | `cd backend && pytest -q` | 72 passed |
| Backend lint / types | `ruff check app tests alembic` · `mypy` | clean · no issues (79 files) |
| Migration (SQLite) | `alembic upgrade head && alembic check && alembic downgrade base` | passed |
| Migration (Postgres DDL) | `alembic upgrade head --sql` with a Postgres URL | renders UUID/JSONB/vector(384)/HNSW; not executed against a live Postgres locally |
| Frontend unit (Vitest) | `npm test` | 11 passed |
| Frontend lint / types / build | `npm run lint` · `npm run typecheck` · `npm run build` | clean · clean · 15 routes built |
| E2E (Playwright, desktop + mobile) | `PW_CHANNEL=chrome npm run test:e2e` | 6 passed, 3 consecutive runs |

## Coverage by area
- **Security regressions (internal review):** spoofed X-Forwarded-For, refresh-token reuse, reset-link
  consumption, single-use voice tickets, voice after logout, image pixel limit, filing verification state.
- **Auth:** register/login/logout, duplicate/weak/terms, CSRF, bearer tokens, refresh rotation,
  password reset + session revocation, enumeration, rate limiting, sessions.
- **Authorization:** cross-user 404 on all case resources and voice tickets, admin role, tampered tokens.
- **Legal RAG:** all 107 sections chunked, clause preservation, retrieval for limitation (EN/HI),
  jurisdiction, fee, metadata propagation, amendment notice, low-confidence behaviour, Hindi expansion.
- **Rules:** pecuniary boundaries, fee table boundaries, limitation (urgent, expired, leap day),
  exclusions, grounding.
- **Extraction:** amounts (₹, lakh, Hindi), dates (numeric, textual, Devanagari, relative, invalid),
  Hindi yes/no/skip, language detection, category signals.
- **Agents:** full offline intake → grounded analysis, one question per turn, retry/skip,
  inference confirmation, Hindi, referral, commercial exclusion, urgent safety, persistence/resume,
  failed tool + retry record, LLM consent gate, excerpt validation, LLM failure fallback, unsafe
  rephrasing rejection, LLM cannot override criminal signals.
- **Documents/filing:** consent gate, malicious uploads, extraction from a generated invoice,
  injection flag, conflicts blocking approval, generate/edit/version, stale approval, blocked
  approval, PDF/DOCX, authorisation, browser assist unavailable, acknowledgement as user-reported,
  reviewer verification.
- **Voice/security:** encryption tamper, injection/citation/guarantee detection, redaction,
  filename sanitising, sentence splitting, ticket + WebSocket turn, bad ticket, foreign origin,
  transcript consent, export/deletion, security headers.
- **Frontend:** dictionary key parity, Hindi coverage, INR formatting, WAV encoder, chat cards;
  E2E landing (EN/HI), route protection, register → describe → confirm → facts → filing gate.

## Security review
A read-only review (subagent) on 2026-10-31 reported 2 high, 4 medium and 6 low findings; all were
fixed with regression tests except registration revealing an existing email (accepted UX trade-off;
mitigated by rate limits). Authorization, approval gates, storage, LLM consent and admin roles were
found sound.

## Manual verification performed
Browser session on the production build: registration, Hindi UI, Hindi text intake with batch
confirmation, voice panel rendering, and a Hindi voice turn over the real WebSocket from the
browser origin (assistant text + 3 sentence TTS events). No console errors.

## Not yet verified (requires hardware or credentials)
Live microphone sessions; Sarvam STT/TTS; Claude API calls; Tesseract OCR; Postgres + pgvector at
runtime; Redis/arq worker; SMTP; S3; browser assist on e-Jagriti.

## Manual voice test protocol (to run when credentials are available)
For each of Hindi, English and code-mixed speech: quiet room, background noise (TV/street), long
pauses mid-answer, interrupting the assistant mid-sentence, a misheard amount (correct it by voice),
airplane-mode for 10 s then resume. Record `voice_sessions.stats` (avg STT, turn, first-audio
latency) and note naturalness issues.

## Rules
Synthetic fixtures only (example.com, invented sellers). No real external services in tests.
