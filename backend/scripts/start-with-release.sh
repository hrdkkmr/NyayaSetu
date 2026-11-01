#!/bin/sh
# Start command for hosts without a separate release step (e.g. Render free plan):
# apply migrations, load the official legal sources (idempotent), then serve.
set -e
alembic upgrade head
python -m app.cli ingest
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
  --proxy-headers --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}"
