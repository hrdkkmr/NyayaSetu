# Known Limitations

## Legal content
- Knowledge base holds three documents: the Act as enacted, the 2021 Jurisdiction Rules (copy
  hosted on a High Court website) and the 2023 fee amendment. Not ingested: consolidated amended Act,
  commencement notifications, principal CDRC Rules 2020, E-Commerce Rules 2020, state rules,
  regulations on complaint format, case law.
- Sources are marked "fetched from official publication"; none has yet been verified by a legal
  reviewer as current.
- The default embedder is lexical (feature hashing); semantic recall needs an embedding API.
- Hindi questions are matched through a reviewed glossary, not translation; unusual phrasing may miss.
- The limitation date is an estimate from the user's date; the legal "cause of action" date can differ.

## Agents
- Without Claude, intake uses patterns: free-text answers are assigned to the question asked, and
  corrections inside long sentences may not be picked up (users can edit facts directly).
- Only the consumer domain has a guided workflow; other domains are referred.
- Claude paths are tested only with a scripted provider (no API key available during development).
- The OpenAI-compatible provider (Grok/Groq) is tested against a mocked HTTP API only. Models that
  support neither `json_schema` nor JSON mode cannot be used; their output fails validation and the
  agents fall back to rules. Smaller models may follow the schema less reliably than Claude.

## Documents
- PDFs are English only (ReportLab built-in fonts; no Indic shaping) and print "Rs." for ₹.
- Templates follow the structure implied by the Act; specific Commission/e-Jagriti formatting
  rules were not available as an official source and must be checked by the user.
- No antivirus scanning; OCR requires Tesseract (not installed in the development environment).

## Filing & tracking
- No automated submission or status polling (no authorised API; OTP/CAPTCHA).
- Browser assist is untested against the live portal and only useful when the backend runs on the
  citizen's own machine.
- e-Jagriti observations (upload rules, flows) date from 2026-10-30 and may change.

## Voice
- Not tested with a live microphone or Sarvam credentials; latency not benchmarked.
- Browser speech recognition handles one language at a time and is unavailable in Firefox.
- Server STT uses Sarvam REST per utterance (≤30 s), not streaming partial transcripts.

## Platform
- PostgreSQL/pgvector, Redis/arq, S3, SMTP, Sentry and OTEL code paths were not executed locally
  (Docker daemon unavailable); CI is configured to run Postgres migrations but has not run yet.
- Registration does not verify email ownership. Google sign-in therefore takes over (and resets the
  password of) an existing account with the same address on first link; reset codes go to the
  registered address.
- Google sign-in needs the web origin listed in the Google OAuth client; it is untested with a live
  client ID.
- The Render + Vercel recipe in DEPLOYMENT_GUIDE.md has not been deployed and verified. On Render's
  free tier the service sleeps when idle, local disk is ephemeral (use S3 storage), and outbound
  SMTP may be blocked by the host (password-reset email then fails; check Render's current policy).
- SQLite development mode serialises writes (`BEGIN IMMEDIATE`); use Postgres for concurrency.
- No MFA, no row-level security, no automated retention purge, no penetration test.
- Voice ticket single-use tracking is per API process (see SECURITY_AND_PRIVACY.md).
