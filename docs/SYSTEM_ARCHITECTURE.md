# System Architecture

## Overview
A modular monolith: one FastAPI application, one arq background worker, one Next.js web app.

```
Citizen (browser / future Android)
   │  HTTPS (same-origin /api/* via Next.js rewrite)      WSS (voice)
   ▼                                                        │
Next.js 15 (App Router, TS, Tailwind)                      │
   │                                                        ▼
   └────────────► FastAPI  /api/v1  ◄──────────── /api/v1/voice/ws
                    │
                    ├─ Auth & sessions (argon2, JWT access + rotating refresh, CSRF)
                    ├─ Case management (cases, facts, deadlines, updates, audit)
                    ├─ Voice service (ticketed WebSocket, Sarvam / browser speech)
                    ├─ LangGraph case workflow
                    │     safety → intake → classification → (referral | ask | research → planning)
                    │     documents → (verification per version)   filing   tracking
                    ├─ Legal knowledge engine (ingest → chunk → embed → hybrid retrieve)
                    ├─ Document engine (validation → extraction; templates → PDF/DOCX)
                    ├─ Integrations (e-Jagriti adapter, Playwright assist, Sarvam, SMTP, S3)
                    └─ Admin/operations
                    │
   PostgreSQL + pgvector · Redis (arq queue, rate limits) · S3-compatible object storage
```

## Boundaries
| Concern | Location | Notes |
|---|---|---|
| User interaction | `frontend/src`, `backend/app/api` | Frontend never performs privileged actions directly. |
| Legal reasoning | `app/agents`, `app/domains/consumer`, `app/legal` | Rules cite provisions; LLM optional and consent-gated. |
| Document generation | `app/documents`, `app/services/documents.py` | Deterministic templates, versioning, verification. |
| Orchestration | `app/agents/graph.py` | LangGraph `StateGraph`, checkpoint in `workflow_instances`. |
| External integrations | `app/integrations` | Adapters with honest capability flags. |
| Persistence | `app/models`, `app/db`, `alembic/` | Portable types (UUID/JSONB/vector on Postgres). |
| Audit | `app/core/audit.py` → `audit_logs` | Scrubbed metadata only. |

## Request lifecycle (message)
1. `POST /cases/{id}/messages` → ownership check → message stored (if transcript consent).
2. `run_case_workflow(trigger="message")`: load checkpoint + facts, invoke graph.
3. Nodes write facts/citations/steps/deadlines; each node logged to `agent_executions`.
4. Durable state checkpointed with optimistic revision; reply + cards returned.

## Background work
`services/jobs.py` records every job in `background_jobs`. With `REDIS_URL` the arq worker runs
them (plus cron: daily deadline reminders 09:00 IST, hourly integration health); otherwise they
run in-process after the response. Jobs: document processing, legal ingestion, reminders, health.

## Configuration
`app/config.py` (pydantic-settings) reads env vars; `.env.example` documents all. Production
start is refused if critical settings are unsafe (`validate_for_production`).

## Environments
- Local: SQLite + local encrypted storage, in-process jobs, browser speech.
- Compose: Postgres/pgvector, Redis, MinIO, API, worker, web.
- Production: Vercel (web) or container; Render/container (API + worker); managed Postgres with
  pgvector; managed Redis; S3-compatible storage. See DEPLOYMENT_GUIDE.md.
