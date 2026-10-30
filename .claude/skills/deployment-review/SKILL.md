---
name: deployment-review
description: Use when changing Dockerfiles, compose, CI, environment variables, or preparing/reviewing a deployment.
---

# Deployment review

## Objective
Safe, reproducible deployments of web (Vercel or container), API + worker (Render or container),
Postgres+pgvector, Redis and S3-compatible storage — configured only through environment variables.

## When to use
`Dockerfile`s, `docker-compose.yml`, `.github/workflows/ci.yml`, `.env.example`,
`docs/DEPLOYMENT_GUIDE.md`, `config.py`.

## Checklist
- [ ] `ENVIRONMENT=production`, `SECRET_KEY` ≥ 32 random chars, `COOKIE_SECURE=true`,
      Postgres `DATABASE_URL`, `EXPOSE_DEV_RESET_TOKENS=false`, explicit `CORS_ORIGINS`
      (the API refuses to start otherwise).
- [ ] `STORAGE_ENCRYPTION_KEY` set and backed up (losing it makes stored documents unreadable).
- [ ] Release step: `alembic upgrade head` then `python -m app.cli ingest`.
- [ ] Worker running (`arq app.worker.WorkerSettings`) with the same env; `REDIS_URL` set.
- [ ] Frontend: `BACKEND_URL` (server-side proxy) and `NEXT_PUBLIC_API_WS_URL` (`wss://…`).
- [ ] TLS at the edge; proxy sets `X-Forwarded-For`.
- [ ] `/health/ready` wired to the platform health check.
- [ ] Sentry DSN / OTLP endpoint optional; Sentry `send_default_pii=False` stays.
- [ ] Admin created with `python -m app.cli create-admin` (password via stdin).
- [ ] Admin → Integration health reviewed; `not_configured` items are expected only when intended.

## Security considerations
No secrets in images, compose files or CI logs. Containers run as non-root users.

## Testing expectations
CI green (backend, frontend, e2e). Postgres migration job passes. Smoke test after deploy:
register → describe problem → analysis → generate documents.

## Common failure scenarios
- Changing `EMBEDDING_DIMENSIONS` in production without a migration.
- Forgetting `NEXT_PUBLIC_API_WS_URL` at *build* time (it is inlined into the client bundle).
- Cross-site cookies: keep the browser on one origin via the Next.js `/api` proxy.
