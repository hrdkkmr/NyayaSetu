# Implementation Status (2026-10-30)

Legend: **Done** = implemented and tested · **Needs credentials** = implemented, awaiting keys/
services to verify · **Partial** · **Not implemented** · **Blocked** = by external authorisation ·
**Excluded** = intentionally excluded for safety.

| Module | Status | Notes |
|---|---|---|
| Auth (register, login, refresh rotation, logout, reset, sessions, CSRF, bearer) | Done | Email delivery: Needs credentials (SMTP) |
| Password reset by 6-digit email code (bilingual HTML email) | Done | Gmail SMTP login verified locally; delivery depends on SMTP |
| Sign in with Google (Google Identity Services ID token) | Needs credentials | Verification tested with locally signed tokens; not run against a live Google client ID |
| Users: profile, preferences, consents, export, deletion request/execution | Done | Automatic retention purge: Not implemented |
| Cases, facts with provenance, timeline, deadlines, updates, archive, activity | Done | |
| Dashboard | Done | Empty states; no sample data |
| LangGraph workflow (persistence, retries, recovery, approval interrupt) | Done | |
| Intake / classification / research / planning / verification agents (rule path) | Done | |
| Same agents with Claude | Needs credentials | Tested with a scripted provider |
| Same agents with an OpenAI-compatible API (xAI Grok, Groq) | Done | Verified live on Groq (`openai/gpt-oss-120b`); backup model `openai/gpt-oss-20b` hand-off verified live |
| Agent trace in turn responses + Live agent telemetry drawer with live provenance | Done | |
| AI status indicator and backup-model routing | Done | |
| Statutory deadlines: limitation (s.69), admissibility target (s.36(2)); user-set legal-notice deadline; .ics + Google Calendar | Done | |
| AI evidence extraction from uploads (quote-checked, user review) | Done | Verified live on Groq with synthetic text; OCR on Render (Tesseract in the Docker image) not yet exercised |
| e-Jagriti local co-pilot bundle (pauses at `HITL_AWAITING_CITIZEN_OTP_AND_SUBMIT`) | Partial | Bundle and script tested offline; never run against the live portal form |
| Legal ingestion + hybrid retrieval + citations | Done | 3 official documents; pgvector path verified by DDL only |
| Consumer rules (forum, fee, limitation, territory, consumer status, reliefs, appeal) | Done | Grounded in ingested provisions |
| Uploads: validation, encryption, extraction, field review, evidence | Done | OCR: Needs credentials (Tesseract binary); antivirus: Not implemented |
| Document generation, versioning, editing, verification, PDF/DOCX | Done | Hindi PDF output: Not implemented |
| Approvals (document + filing authorisation, hash-bound) | Done | |
| e-Jagriti guided filing + acknowledgement + reviewer verification | Done | |
| e-Jagriti browser assist (Playwright) | Partial | Implemented, disabled by default, not run against the live portal |
| e-Jagriti automated submission | Blocked | No authorised public API |
| CAPTCHA/OTP automation | Excluded | |
| Official status polling | Blocked / Excluded | CAPTCHA-protected; no API |
| Voice WebSocket, browser speech, VAD, barge-in, reconnection | Done | Live-microphone quality: not yet verified |
| Sarvam STT/TTS | Needs credentials | Fields per docs.sarvam.ai |
| Realtime speech-to-speech experiment | Not implemented | Must not bypass the workflow |
| Notifications + deadline reminders | Done | Email: Needs credentials |
| Background jobs (in-process + arq worker, cron) | Done (in-process) | arq/Redis: Needs credentials (Redis) |
| Admin console (health, sources, jobs, agents, workflows, audit, filings, deletions) | Done | |
| Frontend (all pages, Hindi/English, accessibility settings) | Done | |
| Docker, compose, CI | Partial | Written; Docker daemon unavailable locally; CI not yet run |
| Observability (Sentry, OpenTelemetry) | Needs credentials | |
| Android app | Not implemented | Out of scope; APIs support bearer tokens |
| Other legal domains | Partial | Detected and referred; no guided workflow |
