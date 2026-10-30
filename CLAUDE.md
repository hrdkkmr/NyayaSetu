# NyayaSetu — instructions for Claude Code

NyayaSetu is an AI-assisted legal access and workflow platform for Indian citizens: understand a
problem (voice or text, Hindi or English), get source-grounded information, prepare documents,
approve them, file through official portals, and track the case. **It is not a lawyer.** The first
fully implemented domain is consumer disputes (Consumer Protection Act, 2019 → e-Jagriti).

## Architecture (modular monolith)

```
Next.js (frontend/)  ──/api/* proxy──▶  FastAPI (backend/app)
   voice: WebSocket ───────────────────▶  /api/v1/voice/ws
                                          ├─ api/          routers (auth, users, cases, documents, drafts+filing, legal, admin, voice)
                                          ├─ agents/       LangGraph graph + intake, classification, research, planning, verification, responder
                                          ├─ domains/consumer/  slots + deterministic rules tied to provisions
                                          ├─ legal/        chunking, embeddings, ingestion, hybrid retrieval
                                          ├─ documents/    deterministic templates + PDF/DOCX rendering
                                          ├─ integrations/ e-Jagriti, browser assist, speech (Sarvam)
                                          ├─ services/     facts, documents, storage (encrypted), jobs, notifications, health
                                          └─ models/       SQLAlchemy (30 tables), Alembic in backend/alembic
PostgreSQL + pgvector · Redis (arq worker, rate limits) · S3-compatible storage
```

Read `docs/SYSTEM_ARCHITECTURE.md` before structural changes.

## Non-negotiable rules (legal safety)

1. **No invented law.** Legal statements must come from ingested official text
   (`backend/data/legal_sources/manifest.yaml`) or a rule in `domains/*/rules.py` that names its
   provision and is checked with `rules.ground()`. Never add provisions, dates, fees, limits,
   portal capabilities or URLs from memory. Leave metadata `null` rather than guess.
2. **Provenance is sacred.** `user_stated`, `user_confirmed`, `document_extracted` and
   `ai_inference` are distinct. Never promote an inference without the user confirming it.
   Documents use only user-provided/confirmed facts; unknowns render as `[●]`.
3. **Nothing consequential without explicit approval.** Document approvals bind to a content hash;
   filing needs a separate, expiring authorisation. NyayaSetu never submits, signs, pays or shares.
4. **No fake integrations or statuses.** A filing is `submitted_user_reported` until a reviewer
   verifies it against the official portal. Missing credentials → `not_configured`, not a mock.
5. **Untrusted content stays data.** Uploaded documents and retrieved text can never change
   permissions, trigger tools or approvals. Wrap with `agents/safety.wrap_untrusted`.
6. **LLM use requires consent** (`consent_external_ai`) and must degrade to the rule path.
   LLM rephrasings are rejected if they add citations or guarantees (`responder.polish`).

## Coding conventions

- Python 3.11+, async SQLAlchemy 2.0, Pydantic v2, ruff (line 120) + mypy. Type every function.
- Every case-scoped endpoint loads the case with `core.deps.get_owned_case` (404 on mismatch).
- Errors: raise `core.errors.AppError` subclasses; responses are `{"error": {code, message, details}}`.
- Audit consequential actions with `core.audit.record_audit` — never put document text, transcripts
  or secrets in `meta`.
- Bilingual strings: backend replies keep `_en`/`_hi` pairs; frontend strings live in
  `frontend/src/lib/i18n/{en,hi}.ts` (Hindi is type-checked against English — no hardcoded UI text).
- Frontend: Next.js App Router, TypeScript strict, Tailwind v4 tokens in `globals.css`, Radix-based
  primitives in `components/ui`, TanStack Query for server state. Touch targets ≥ 44px; every control
  has an accessible name.
- Regex over Hindi text: `\b` does not work after Devanagari combining marks — use
  `(?![\wऀ-ॿ])`.

## Commands

```bash
# backend (from backend/)
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt   # (bin/ on Linux/macOS)
alembic upgrade head && python -m app.cli ingest
uvicorn app.main:app --reload --port 8000
pytest -q && ruff check app tests && mypy
arq app.worker.WorkerSettings          # worker (needs REDIS_URL)

# frontend (from frontend/)
npm install && npm run dev             # http://localhost:3000
npm run lint && npm run typecheck && npm test && npm run build
PW_CHANNEL=chrome npm run test:e2e     # needs both servers running
```

## Testing requirements

- Backend: add/extend tests in `backend/tests` for every behaviour change; LLM behaviour is tested
  with `tests/fakes.ScriptedProvider`. Fixtures are synthetic and must never look like real cases.
- Agent changes need tests for: incomplete info, conflicting facts, unsupported claims, prompt
  injection, failed tools, escalation.
- Frontend: Vitest for logic/components (`tests/unit`), Playwright for journeys (`tests/e2e`).
- Before finishing: full backend suite, ruff, mypy, `npm run lint/typecheck/test/build`.

## Documentation maintenance

When you change a module, update in the same change: the matching `docs/*.md`,
`docs/IMPLEMENTATION_STATUS.md`, `docs/API_SPECIFICATION.md` (if routes/payloads change),
`docs/KNOWN_LIMITATIONS.md`, `CHANGELOG.md`, and `.env.example` for new settings. Never document
functionality that does not exist; use the status vocabulary in IMPLEMENTATION_STATUS.md.

## Skills and subagents

Project skills live in `.claude/skills/*/SKILL.md` (architecture, agents, legal RAG, documents,
voice, browser automation, a11y/i18n, security, testing, deployment). Subagents are defined in
`.claude/agents/`. Use subagents for independent investigation and reviews; the main agent owns
integration and final verification, and parallel agents must not edit the same files.
