# API Specification (v1)

Base path `/api/v1`. Interactive OpenAPI docs at `/api/docs` (disabled in production).
JSON everywhere except uploads (multipart) and downloads (binary).

## Conventions
- **Auth (web):** httpOnly cookies `ns_access`, `ns_refresh`; unsafe methods must send
  `X-CSRF-Token` equal to the `ns_csrf` cookie.
- **Auth (native/Android):** send `X-Client-Type: mobile` on register/login/refresh to receive
  `access_token`/`refresh_token` in the body; then `Authorization: Bearer <access>` (CSRF exempt).
- **Errors:** `{"error": {"code", "message", "details"}}`. Common codes: `unauthenticated`,
  `csrf_failed`, `forbidden`, `not_found` (also for other users' resources), `validation_error`,
  `rate_limited` (429), `approval_required` (428), `version_mismatch` (409),
  `integration_unavailable` (503).

## Auth `/auth`
| Method | Path | Body / notes |
|---|---|---|
| POST | `/register` | `{email, full_name, password, phone?, language, accept_terms:true}` → `AuthResponse` |
| POST | `/login` | `{email, password}` |
| POST | `/refresh` | cookie or `{refresh_token}`; rotates the token |
| POST | `/logout` | revokes session |
| POST | `/password/forgot` | `{email}` → generic message; emails a 6-digit code valid `PASSWORD_RESET_TTL_MINUTES` (dev: `dev_reset_code`) |
| POST | `/password/reset` | `{email, code, new_password}`; code burned after `PASSWORD_RESET_MAX_ATTEMPTS` wrong tries; revokes all sessions. Errors `reset_invalid`, `reset_expired` |
| GET | `/providers` | `{google_client_id: string \| null}` — sign-in methods to offer |
| POST | `/google` | `{credential, language?}` (Google ID token) → `AuthResponse`; creates or links the account by verified email. Errors `google_invalid`, `google_email_unverified` (401), `google_not_configured`, `google_unreachable` (503) |
| GET | `/me` | current user + preferences |

## Users `/users/me`
`GET ""`, `PATCH ""` (`full_name`, `phone`), `PATCH /preferences` (language, text_scale,
high_contrast, reduce_motion, voice_provider, speech_rate, autoplay_voice, consent_* flags),
`POST /password`, `GET /sessions`, `DELETE /sessions/{id}`, `GET /export`,
`POST|DELETE /deletion-request`.

## Cases
| Method | Path | Notes |
|---|---|---|
| GET | `/dashboard` | cases, deadlines, documents to review, pending steps, filings, notifications |
| GET/POST | `/cases` | create: `{language, title?, description?, modality}`; with description returns the first `turn` |
| GET | `/cases/{id}` | detail: facts, parties, timeline, missing info, analysis, workflow steps, deadlines, counts |
| PATCH | `/cases/{id}` | rename |
| POST | `/cases/{id}/archive?archived=bool` | |
| GET/POST | `/cases/{id}/messages` | POST `{text, modality, language?}` → `TurnResult` (user + assistant message, cards, phase, asked_slot) |
| POST | `/cases/{id}/facts` | `{key, value}` user-confirmed edit |
| POST | `/cases/{id}/facts/{fid}/confirm` · `/reject` | |
| POST | `/cases/{id}/analysis/refresh` | re-run research + planning |
| GET | `/cases/{id}/research` | citations with document metadata, rule outcomes, limitations |
| POST | `/cases/{id}/workflow/steps/{key}?status=done|pending` | user-owned steps only |
| GET/POST | `/cases/{id}/deadlines` · PATCH `/deadlines/{did}` | |
| GET/POST | `/cases/{id}/updates` | user-reported updates (hearing adds a deadline) |
| GET | `/cases/{id}/activity` · `/approvals` | |

**Card types** in assistant messages: `confirm_facts`, `question`, `rule_outcome`, `resources`,
`sources`, `missing_facts`, `documents`, `filing_ready`.

## Documents
| Method | Path | Notes |
|---|---|---|
| POST | `/cases/{id}/uploads` | multipart `file`; requires `consent_document_storage`; PDF/DOCX/JPG/PNG ≤ 20 MB |
| GET | `/cases/{id}/uploads[/{uid}]` | detail includes extraction fields + text preview |
| GET | `/cases/{id}/uploads/{uid}/file` | decrypted download (audited) |
| DELETE | `/cases/{id}/uploads/{uid}` | |
| POST | `/cases/{id}/uploads/{uid}/accept-fields` | `{fields:[amount_paid|purchase_date|seller_name]}` → document facts |
| GET/POST | `/cases/{id}/evidence` · PATCH/DELETE `/evidence/{eid}` | auto labels `Annexure A-n` |

## Drafts, approvals, filing
| Method | Path | Notes |
|---|---|---|
| POST | `/cases/{id}/drafts/generate` | runs document agent; returns missing facts if blocked |
| GET | `/cases/{id}/drafts[/{did}]` | detail includes versions, approvals, approval statement |
| PUT | `/cases/{id}/drafts/{did}` | `{edits:{block_id:text}, note?}` → new version |
| GET | `/cases/{id}/drafts/{did}/download?format=pdf|docx&version=n` | |
| POST | `/cases/{id}/drafts/{did}/approve` | `{version_number, content_sha256, statement_accepted, acknowledge_warnings}` |
| POST | `/cases/{id}/drafts/{did}/revoke-approval` | |
| GET | `/cases/{id}/filing` | capabilities, readiness, blockers, guided steps, data sheet, record |
| POST | `/cases/{id}/filing/authorize` | `{statement_accepted, allow_browser_assist}` (7-day, bound to approved versions) |
| POST | `/cases/{id}/filing/start` | `{mode: guided|browser_assist}` |
| POST | `/cases/{id}/filing/{fid}/checklist` | `{key, done}` |
| POST | `/cases/{id}/filing/{fid}/browser-assist` | local deployments only |
| POST | `/cases/{id}/filing/{fid}/acknowledgement` | `{acknowledgement_number, submitted_on, document_id?}` → `submitted_user_reported` |

## Legal, notifications, voice
`GET /legal/search?q=&domain=&limit=`, `GET /legal/sources`, `GET /legal/chunks/{id}`.
`GET /notifications?unread_only=`, `POST /notifications/{id}/read`, `POST /notifications/read-all`.
`GET /voice/config`, `POST /voice/ticket {case_id}` → 60 s ticket, `WS /voice/ws?ticket=` (protocol
in VOICE_AGENT_DESIGN.md).

## Admin `/admin` (role admin; some routes also legal_reviewer)
`GET /overview`, `GET /health?external=`, `GET /legal-sources`, `POST /legal-sources/ingest`,
`POST /legal-sources/{key}/verification` (reviewer), `GET /jobs`, `POST /jobs/{kind}`,
`POST /jobs/{id}/retry`, `GET /agent-executions`, `GET /workflows`, `GET /audit`,
`GET /filings`, `POST /filings/{id}/verify` (reviewer), `GET /deletion-requests`,
`POST /deletion-requests/{user_id}/execute`.

## Health
`GET /health` (liveness), `GET /health/ready` (database).
