---
name: testing-qa
description: Use when writing or fixing tests, verifying a change end-to-end, or preparing the final verification of a task.
---

# Testing & QA

## Objective
Reproducible evidence that each subsystem works — and honest reporting when it does not.

## When to use
After any behaviour change; before claiming completion.

## Suites
| Suite | Command | Notes |
|---|---|---|
| Backend unit/integration | `cd backend && pytest -q` | SQLite temp DB, real legal sources ingested once per session |
| Backend lint/types | `ruff check app tests alembic && mypy` | |
| Migrations | `alembic upgrade head && alembic check && alembic downgrade base` | CI also runs on Postgres+pgvector |
| Frontend unit | `cd frontend && npm test` | Vitest + Testing Library |
| Frontend static | `npm run lint && npm run typecheck && npm run build` | |
| E2E | `PW_CHANNEL=chrome npm run test:e2e` | needs backend :8000 and frontend :3000 |

## Rules
- Fixtures are synthetic (example.com emails, invented sellers) and never presented as real cases,
  users, filings or government records.
- LLM paths: use `tests/fakes.ScriptedProvider`; never call real APIs in tests.
- A failing test is reported with its output; do not weaken assertions to make it pass without
  understanding the cause.
- E2E across two device projects runs concurrently — it already caught a SQLite locking bug.

## Coverage expectations (agents)
Incomplete info, conflicting facts, ambiguous complaint, unsupported claims, missing sources,
prompt injection, uncertain classification, escalation, workflow interruption, failed tools.

## Common failure scenarios
- `MissingGreenlet` → lazy-load in async; `database is locked` → transaction held across a job.
- Email validator rejects `.test` domains; use `example.com`.
- Vitest needs `esbuild.jsx = "automatic"` (Next uses `jsx: preserve`) and explicit `cleanup()`.
