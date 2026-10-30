---
name: system-architecture
description: Use when adding a module, changing boundaries between API/agents/services/integrations, adding tables, or deciding where new code belongs in NyayaSetu.
---

# System architecture

## Objective
Keep NyayaSetu a clean modular monolith: one FastAPI app, one arq worker, one Next.js app, clear
boundaries between user interaction, legal reasoning, document generation, orchestration,
integrations, persistence and audit.

## When to use
- Adding a router, service, agent, integration or table.
- Moving logic between layers, or adding a new legal domain.
- Any change touching more than two of `api/`, `agents/`, `services/`, `integrations/`, `models/`.

## Layering (import direction is downward only)
```
api/            HTTP + WebSocket; auth, ownership, validation, serialisation (api/serializers.py)
agents/         LangGraph graph (agents/graph.py) and agents; no HTTP concerns
domains/<x>/    slots + deterministic rules for one legal domain
services/       facts, documents, storage, jobs, notifications, health (reusable, DB-aware)
legal/          ingestion, chunking, embeddings, retrieval
documents/      templates + render (pure functions)
integrations/   external systems behind adapters (ejagriti, browser_assist, speech)
models/ db/     SQLAlchemy models, portable types (db/types.py), sessions
core/           config-independent primitives: errors, security, deps, audit, ratelimit, logging
```
- Routers never call vendor SDKs directly; agents never import `api/`.
- The frontend never performs privileged actions itself: every approval/filing goes through the API.
- New tables: add the model, export it in `models/__init__.py`, then
  `alembic revision --autogenerate -m "..."` and review the file (custom types render as
  `app.db.types.*`). Postgres-only DDL goes behind `op.get_bind().dialect.name == "postgresql"`.
- New legal domain: `domains/<name>/{slots.py,rules.py}`, templates in `documents/`, a classifier
  category, manifest entries for its official sources, and tests.

## Security considerations
- Ownership is enforced in `core/deps.get_owned_case` — every case-scoped query must use it or
  filter by `case_id` obtained from it.
- Secrets only via `config.Settings`; never in DB rows (`integration_configs` stores non-secret settings).

## Testing expectations
- Architecture changes keep `pytest`, `ruff`, `mypy`, `alembic check` green.
- New endpoints get an authorization test (another user receives 404).

## Common failure scenarios
- Lazy-loading a relationship in async code → `MissingGreenlet`. Load with `selectinload` or
  `await db.refresh(obj, attribute_names=[...])` before serialising.
- Holding a DB transaction open while a background job writes (SQLite locks). Commit before dispatch.
- Adding a JSON column without `JSONType` (breaks JSONB on Postgres).
