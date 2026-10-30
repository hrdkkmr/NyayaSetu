"""Restricted operations console. Admin role required for every route.

Admins see operational metadata (statuses, errors, counts, audit actions) - not
citizens' message transcripts or document contents.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import serializers as ser
from app.api.legal import _doc
from app.core.audit import record_audit
from app.core.deps import RequestContext, require_roles
from app.core.errors import ConflictError, NotFoundError
from app.db.base import utcnow
from app.db.session import get_db
from app.models import (
    AgentExecution,
    AuditLog,
    BackgroundJob,
    Case,
    CaseUpdate,
    FilingRecord,
    LegalDocument,
    UploadedDocument,
    User,
    WorkflowInstance,
)
from app.models.enums import CaseStatus, FilingStatus, UpdateSource, UserRole, VerificationStatus, WorkflowStatus
from app.services.health import check_integrations
from app.services.jobs import create_job, dispatch
from app.services.storage import get_storage, purge_voice_audio

router = APIRouter(prefix="/admin", tags=["admin"])
admin_only = require_roles(UserRole.ADMIN)
reviewer = require_roles(UserRole.ADMIN, UserRole.LEGAL_REVIEWER)


class VerifyDocIn(BaseModel):
    status: Literal["verified_by_reviewer", "stale", "unverified"]
    note: str = Field(min_length=5, max_length=1000)


class VerifyFilingIn(BaseModel):
    official_reference: str = Field(min_length=3, max_length=500)
    note: str | None = Field(default=None, max_length=1000)


@router.get("/overview")
async def overview(_: RequestContext = Depends(admin_only), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    since = utcnow() - timedelta(days=1)

    async def count(stmt: Any) -> int:
        return int(await db.scalar(stmt) or 0)

    return {
        "users": await count(select(func.count()).select_from(User)),
        "cases": await count(select(func.count()).select_from(Case)),
        "cases_needing_review": await count(select(func.count()).select_from(Case).where(
            Case.status == CaseStatus.NEEDS_PROFESSIONAL_REVIEW)),
        "uploads": await count(select(func.count()).select_from(UploadedDocument)),
        "failed_jobs_24h": await count(select(func.count()).select_from(BackgroundJob).where(
            BackgroundJob.status == "failed", BackgroundJob.created_at >= since)),
        "failed_agent_runs_24h": await count(select(func.count()).select_from(AgentExecution).where(
            AgentExecution.status == "failed", AgentExecution.created_at >= since)),
        "workflows_with_errors": await count(select(func.count()).select_from(WorkflowInstance).where(
            WorkflowInstance.last_error.is_not(None))),
        "deletion_requests": await count(select(func.count()).select_from(User).where(
            User.deletion_requested_at.is_not(None))),
        "filings_awaiting_verification": await count(select(func.count()).select_from(FilingRecord).where(
            FilingRecord.status == FilingStatus.SUBMITTED_USER_REPORTED)),
    }


@router.get("/health")
async def integration_health(external: bool = True, _: RequestContext = Depends(admin_only),
                             db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return await check_integrations(db, include_external=external)


@router.get("/legal-sources")
async def legal_sources(_: RequestContext = Depends(reviewer), db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
    docs = (await db.scalars(select(LegalDocument).order_by(LegalDocument.key))).all()
    return [{**_doc(d), "ingestion_error": d.ingestion_error} for d in docs]


@router.post("/legal-sources/ingest")
async def trigger_ingest(background: BackgroundTasks, fetch_live: bool = False, force: bool = False,
                         ctx: RequestContext = Depends(admin_only), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    job = await create_job(db, "ingest_legal_sources", {"fetch_live": fetch_live, "force": force})
    await record_audit(db, action="admin.ingest", actor_user_id=ctx.user.id, ip_hash=ctx.ip_hash,
                       meta={"fetch_live": fetch_live, "force": force})
    await db.commit()
    await dispatch(job, background)
    return {"job_id": str(job.id), "status": job.status}


@router.post("/legal-sources/{key}/verification")
async def set_verification(key: str, payload: VerifyDocIn, ctx: RequestContext = Depends(reviewer),
                           db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    doc = await db.scalar(select(LegalDocument).where(LegalDocument.key == key))
    if doc is None:
        raise NotFoundError("Source not found.")
    doc.verification_status = VerificationStatus(payload.status)
    doc.verification_note = f"{payload.note} (by reviewer)"
    doc.verified_at = utcnow()
    await record_audit(db, action="admin.legal_verification", actor_user_id=ctx.user.id, ip_hash=ctx.ip_hash,
                       resource_type="legal_document", resource_id=doc.id, meta={"status": payload.status})
    return _doc(doc)


@router.get("/jobs")
async def jobs(status: str | None = None, limit: int = Query(default=50, le=200), _: RequestContext = Depends(admin_only),
               db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
    stmt = select(BackgroundJob)
    if status:
        stmt = stmt.where(BackgroundJob.status == status)
    rows = (await db.scalars(stmt.order_by(BackgroundJob.created_at.desc()).limit(limit))).all()
    return [{"id": str(j.id), "kind": j.kind, "status": j.status, "attempts": j.attempts, "error": j.error,
             "result": j.result, "created_at": ser.iso(j.created_at), "started_at": ser.iso(j.started_at),
             "finished_at": ser.iso(j.finished_at)} for j in rows]


@router.post("/jobs/{kind}")
async def run_job_now(kind: Literal["deadline_reminders", "integration_health"], background: BackgroundTasks,
                      ctx: RequestContext = Depends(admin_only), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    job = await create_job(db, kind, {})
    await record_audit(db, action=f"admin.job.{kind}", actor_user_id=ctx.user.id, ip_hash=ctx.ip_hash)
    await db.commit()
    await dispatch(job, background)
    return {"job_id": str(job.id)}


@router.post("/jobs/{job_id}/retry")
async def retry_job(job_id: uuid.UUID, background: BackgroundTasks, ctx: RequestContext = Depends(admin_only),
                    db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    job = await db.get(BackgroundJob, job_id)
    if job is None:
        raise NotFoundError("Job not found.")
    job.status = "queued"
    await db.commit()
    await dispatch(job, background)
    return {"job_id": str(job.id)}


@router.get("/agent-executions")
async def agent_executions(status: str | None = None, agent: str | None = None,
                           limit: int = Query(default=100, le=500), _: RequestContext = Depends(admin_only),
                           db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
    stmt = select(AgentExecution)
    if status:
        stmt = stmt.where(AgentExecution.status == status)
    if agent:
        stmt = stmt.where(AgentExecution.agent == agent)
    rows = (await db.scalars(stmt.order_by(AgentExecution.created_at.desc()).limit(limit))).all()
    return [{"id": str(e.id), "agent": e.agent, "status": e.status, "provider": e.provider, "model": e.model,
             "attempt": e.attempt, "latency_ms": e.latency_ms, "error": e.error, "summary": e.summary,
             "case_id": str(e.case_id) if e.case_id else None, "created_at": ser.iso(e.created_at)} for e in rows]


@router.get("/workflows")
async def workflows(only_errors: bool = True, _: RequestContext = Depends(admin_only),
                    db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
    stmt = select(WorkflowInstance)
    if only_errors:
        stmt = stmt.where((WorkflowInstance.last_error.is_not(None)) | (WorkflowInstance.status == WorkflowStatus.FAILED))
    rows = (await db.scalars(stmt.order_by(WorkflowInstance.updated_at.desc()).limit(100))).all()
    return [{"id": str(w.id), "case_id": str(w.case_id), "status": w.status, "phase": (w.state or {}).get("phase"),
             "current_node": w.current_node, "revision": w.revision, "last_error": w.last_error,
             "updated_at": ser.iso(w.updated_at)} for w in rows]


@router.get("/audit")
async def audit(action: str | None = None, limit: int = Query(default=100, le=500), _: RequestContext = Depends(admin_only),
                db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action.like(f"{action}%"))
    rows = (await db.scalars(stmt.order_by(AuditLog.created_at.desc()).limit(limit))).all()
    return [{"id": str(r.id), "action": r.action, "actor_type": r.actor_type,
             "actor_user_id": str(r.actor_user_id) if r.actor_user_id else None, "resource_type": r.resource_type,
             "resource_id": r.resource_id, "case_id": str(r.case_id) if r.case_id else None, "outcome": r.outcome,
             "meta": r.meta, "created_at": ser.iso(r.created_at)} for r in rows]


@router.get("/filings")
async def filings(_: RequestContext = Depends(reviewer), db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
    rows = (await db.scalars(select(FilingRecord).order_by(FilingRecord.updated_at.desc()).limit(200))).all()
    return [{**ser.filing(f), "case_id": str(f.case_id)} for f in rows]


@router.post("/filings/{filing_id}/verify")
async def verify_filing(filing_id: uuid.UUID, payload: VerifyFilingIn, ctx: RequestContext = Depends(reviewer),
                        db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """A reviewer confirms a filing against the official portal and records where they checked it."""
    record = await db.get(FilingRecord, filing_id)
    if record is None:
        raise NotFoundError("Filing not found.")
    if record.status != FilingStatus.SUBMITTED_USER_REPORTED or not record.acknowledgement_number:
        raise ConflictError("Only a filing the citizen has reported as submitted can be verified.",
                            code="not_submitted")
    record.status = FilingStatus.VERIFIED
    record.verified_at = utcnow()
    case = await db.get(Case, record.case_id)
    if case is not None:
        case.status = CaseStatus.FILED_VERIFIED
    db.add(CaseUpdate(case_id=record.case_id, source=UpdateSource.OFFICIAL_PORTAL, update_type="filing",
                      title=f"Filing {record.acknowledgement_number} confirmed on the official portal",
                      body=payload.note, verified=True, source_reference=payload.official_reference,
                      created_by_user_id=ctx.user.id))
    await record_audit(db, action="admin.filing_verified", actor_user_id=ctx.user.id, ip_hash=ctx.ip_hash,
                       resource_type="filing_record", resource_id=record.id, case_id=record.case_id)
    return ser.filing(record)


@router.get("/deletion-requests")
async def deletion_requests(_: RequestContext = Depends(admin_only), db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
    rows = (await db.scalars(select(User).where(User.deletion_requested_at.is_not(None)))).all()
    return [{"user_id": str(u.id), "requested_at": ser.iso(u.deletion_requested_at)} for u in rows]


@router.post("/deletion-requests/{user_id}/execute")
async def execute_deletion(user_id: uuid.UUID, ctx: RequestContext = Depends(admin_only),
                           db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    user = await db.get(User, user_id)
    if user is None or user.deletion_requested_at is None:
        raise NotFoundError("No pending deletion request for this user.")
    uploads = (await db.scalars(select(UploadedDocument).where(UploadedDocument.user_id == user.id))).all()
    for upload in uploads:
        await get_storage().delete(upload.storage_key)
    await purge_voice_audio(db, user.id)
    await db.delete(user)  # cascades to cases, facts, messages, documents, sessions
    await record_audit(db, action="admin.user_deleted", actor_user_id=ctx.user.id, ip_hash=ctx.ip_hash,
                       resource_type="user", resource_id=user_id)
    return {"message": "User and associated data deleted."}
