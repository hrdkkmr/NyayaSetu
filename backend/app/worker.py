"""arq worker. Run with: `arq app.worker.WorkerSettings` (requires REDIS_URL)."""

from __future__ import annotations

from typing import Any

from arq import cron
from arq.connections import RedisSettings

from app.config import get_settings
from app.core.logging import configure_logging
from app.db.session import session_scope
from app.services.jobs import create_job, run_job


async def run_background_job(_ctx: dict[str, Any], job_id: str) -> None:
    await run_job(job_id)


async def _scheduled(kind: str) -> None:
    async with session_scope() as db:
        job = await create_job(db, kind, {})
        job_id = str(job.id)
    await run_job(job_id)


async def daily_reminders(_ctx: dict[str, Any]) -> None:
    await _scheduled("deadline_reminders")


async def hourly_health(_ctx: dict[str, Any]) -> None:
    await _scheduled("integration_health")


async def startup(_ctx: dict[str, Any]) -> None:
    configure_logging(get_settings().log_level)


class WorkerSettings:
    functions = [run_background_job]
    cron_jobs = [  # type: ignore[list-item]
        cron(daily_reminders, hour={3}, minute={30}),  # type: ignore[arg-type]  # 09:00 IST
        cron(hourly_health, minute={5}),  # type: ignore[arg-type]
    ]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url or "redis://localhost:6379")
    max_tries = 3
    job_timeout = 600
