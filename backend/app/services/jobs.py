"""Background jobs.

Every job is recorded in `background_jobs` so administrators can see what ran and
what failed. With REDIS_URL set, jobs are executed by the arq worker
(`arq app.worker.WorkerSettings`); otherwise they run in-process after the response.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.base import utcnow
from app.db.session import session_scope
from app.models import BackgroundJob
from app.models.enums import JobStatus

logger = logging.getLogger(__name__)

Handler = Callable[[AsyncSession, dict[str, Any]], Awaitable[dict[str, Any]]]
HANDLERS: dict[str, Handler] = {}


def handler(kind: str) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        HANDLERS[kind] = fn
        return fn

    return register


async def create_job(db: AsyncSession, kind: str, payload: dict[str, Any]) -> BackgroundJob:
    job = BackgroundJob(kind=kind, payload=payload, status=JobStatus.QUEUED)
    db.add(job)
    await db.flush()
    return job


async def run_job(job_id: str) -> None:
    """Execute a job in its own session; failures are recorded, never raised."""
    from app.services import job_handlers  # noqa: F401 - registers handlers

    async with session_scope() as db:
        job = await db.get(BackgroundJob, uuid.UUID(job_id))
        if job is None or job.status == JobStatus.SUCCEEDED:
            return
        job.status = JobStatus.RUNNING
        job.attempts += 1
        job.started_at = utcnow()
        await db.commit()
        try:
            result = await HANDLERS[job.kind](db, job.payload)
            job.result = result or {}
            job.status = JobStatus.SUCCEEDED
            job.error = None
        except Exception as exc:  # noqa: BLE001
            logger.exception("Job %s (%s) failed", job.id, job.kind)
            await db.rollback()
            job = await db.get(BackgroundJob, uuid.UUID(job_id))
            assert job is not None
            job.status = JobStatus.FAILED
            job.error = f"{type(exc).__name__}: {str(exc)[:500]}"
        job.finished_at = utcnow()


async def dispatch(job: BackgroundJob, background: BackgroundTasks | None) -> None:
    redis_url = get_settings().redis_url
    if redis_url:
        try:
            from arq import create_pool
            from arq.connections import RedisSettings

            pool = await create_pool(RedisSettings.from_dsn(redis_url))
            await pool.enqueue_job("run_background_job", str(job.id))
            await pool.aclose()
            return
        except Exception:  # noqa: BLE001
            logger.warning("Could not enqueue to Redis; running job in-process")
    if background is not None:
        background.add_task(run_job, str(job.id))
    else:
        await run_job(str(job.id))
