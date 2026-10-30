# NyayaSetu

**Justice should be accessible, not complicated.**

NyayaSetu helps Indian citizens understand a legal problem by voice or text, in Hindi or English. It checks official legal sources, explains the citizen's options, and prepares documents for them to review. It then guides filing on official portals and tracks the case. It is an AI legal-information and paperwork assistant, **not a lawyer**. It never files, signs, pays or shares anything without the user's explicit approval.

The first fully implemented domain is **consumer disputes**: the Consumer Protection Act, 2019, with complaints filed on e-Jagriti.

## Quick start (local, no Docker)

Requires Python 3.11+ and Node 20+.

```bash
# Backend
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt     # Linux/macOS: .venv/bin/pip
.venv/Scripts/alembic upgrade head                    # SQLite by default (backend/nyayasetu.db)
.venv/Scripts/python -m app.cli ingest                # ingest official legal sources (bundled snapshots)
.venv/Scripts/uvicorn app.main:app --reload --port 8000

# Frontend (second terminal)
cd frontend
npm install
npm run dev                                           # http://localhost:3000
```

Optional steps:

```bash
# Create an admin (reads the password from stdin)
python -m app.cli create-admin admin@example.org "Admin Name"

# Background worker (needs REDIS_URL); without Redis, jobs run in-process
arq app.worker.WorkerSettings
```

## Full stack with Docker

```bash
cp .env.example .env    # set SECRET_KEY and STORAGE_ENCRYPTION_KEY
docker compose up --build
```

This runs Postgres with pgvector, Redis, MinIO, migrations and ingestion, the API, the worker and the web app.

## Tests and checks

| What | Command |
|---|---|
| Backend tests (72) | `cd backend && .venv/Scripts/python -m pytest -q` |
| Backend lint and types | `ruff check app tests alembic && mypy` |
| Migrations | `alembic upgrade head && alembic check && alembic downgrade base` |
| Frontend unit tests (11) | `cd frontend && npm test` |
| Frontend lint, types and build | `npm run lint && npm run typecheck && npm run build` |
| End-to-end, desktop and mobile (6) | `PW_CHANNEL=chrome npm run test:e2e` (needs both servers running) |

## Configuration

All settings are environment variables, documented in [`.env.example`](.env.example). Every external integration is optional:

- **Anthropic Claude:** used only for users who consent to external AI processing.
- **Sarvam AI speech:** without a key, the browser's own speech features are used.
- **Others:** SMTP, S3, Redis, Tesseract OCR, Sentry, OpenTelemetry and Playwright browser assist.

A missing credential shows as `not_configured` on the admin health page, and the rest of the app keeps working.

## Project layout

```
backend/   FastAPI app, LangGraph agents, legal RAG, document engine, Alembic, tests
frontend/  Next.js App Router UI (Hindi/English), voice client, Vitest + Playwright tests
.claude/   Claude Code skills and subagents
CLAUDE.md  Rules for working on this codebase (legal safety, conventions, commands)
```

See `CLAUDE.md` for architecture, rules and conventions.
