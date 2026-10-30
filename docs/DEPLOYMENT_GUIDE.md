# Deployment Guide

## Components
| Component | Suggested host | Start command |
|---|---|---|
| Web (Next.js) | Vercel, or container (`frontend/Dockerfile`, standalone output) | `node server.js` |
| API (FastAPI) | Render / container (`backend/Dockerfile`) | `uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers` |
| Worker (arq) | Render background worker / container | `arq app.worker.WorkerSettings` |
| Release step | Render pre-deploy / one-off job | `alembic upgrade head && python -m app.cli ingest` |
| Database | Managed PostgreSQL 15+ with the `vector` extension | — |
| Redis | Managed Redis | — |
| Storage | S3-compatible bucket (private) | — |

## Required environment (production)
API + worker: `ENVIRONMENT=production`, `SECRET_KEY` (≥32 random chars), `DATABASE_URL`
(`postgresql+asyncpg://…`), `REDIS_URL`, `COOKIE_SECURE=true`, `CORS_ORIGINS=https://your-web-origin`,
`PUBLIC_APP_URL`, `STORAGE_BACKEND=s3`, `S3_*`, `STORAGE_ENCRYPTION_KEY` (base64 32 bytes — back it
up; losing it makes stored documents unreadable), `SMTP_*` for password resets/reminders.
Optional: `ANTHROPIC_API_KEY`, `SARVAM_API_KEY`, `EMBEDDING_*`, `SENTRY_DSN`,
`OTEL_EXPORTER_OTLP_ENDPOINT`.

Web: `BACKEND_URL=https://api.your-domain` (server-side proxy target),
`NEXT_PUBLIC_API_WS_URL=wss://api.your-domain` (**build-time** variable).

The API refuses to start in production with unsafe settings (dev secret, insecure cookies, SQLite,
dev reset tokens, wildcard CORS).

## Steps
1. Provision Postgres (enable `vector`), Redis, bucket.
2. Deploy API image; run the release step; check `/health/ready`.
3. Deploy worker with the same environment.
4. Deploy web with `BACKEND_URL` and `NEXT_PUBLIC_API_WS_URL`.
5. Create an admin: `echo "<password>" | python -m app.cli create-admin admin@org "Name"`.
6. Sign in → Operations → Integration health; confirm intended services show OK.
7. Smoke test: register, describe a consumer problem, reach analysis, generate drafts, download PDF.

## Local full stack
```bash
cp .env.example .env    # set SECRET_KEY, STORAGE_ENCRYPTION_KEY
docker compose up --build
```

## CI
`.github/workflows/ci.yml`: backend (ruff, mypy, pytest, migrations + ingestion on
pgvector/pgvector:pg16), frontend (lint, typecheck, unit, build), e2e (Playwright Chromium against a
running stack). *The workflow has been written but has not yet run on GitHub.*

## Operations
- Changing `EMBEDDING_DIMENSIONS` requires a new migration and `python -m app.cli ingest --force`.
- Re-check sources periodically: `python -m app.cli ingest --live` flags changed official PDFs.
- Rotate `SECRET_KEY` → all sessions end; `STORAGE_ENCRYPTION_KEY` rotation needs re-encryption
  (not automated).
