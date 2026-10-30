from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import serializers as ser
from app.config import get_settings
from app.core.audit import record_audit
from app.core.deps import RequestContext, get_context, get_owned_case
from app.core.errors import AppError, NotFoundError
from app.core.security import sha256_hex
from app.db.base import utcnow
from app.db.session import get_db
from app.domains.consumer.slots import SLOT_BY_KEY
from app.models import Case, EvidenceItem, UploadedDocument
from app.models.enums import DocumentStatus, FactProvenance
from app.services import facts as fact_service
from app.services.document_processing import UploadRejected, validate_upload
from app.services.jobs import create_job, dispatch
from app.services.storage import get_storage, load_decrypted, store_encrypted

router = APIRouter(tags=["documents"])

# Extracted field → case fact key. Other fields are informational only.
FIELD_TO_FACT = {"amount_paid": "amount_paid", "purchase_date": "purchase_date", "seller_name": "seller_name"}


class AcceptFields(BaseModel):
    fields: list[str] = Field(min_length=1, max_length=10)


class EvidenceIn(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    description: str | None = Field(default=None, max_length=2000)
    evidence_date: date | None = None
    document_id: uuid.UUID | None = None
    evidence_type: str = Field(default="document", max_length=64)


class EvidencePatch(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=300)
    description: str | None = Field(default=None, max_length=2000)
    evidence_date: date | None = None
    order_index: int | None = Field(default=None, ge=0, le=500)


async def _owned_upload(db: AsyncSession, case: Case, upload_id: uuid.UUID) -> UploadedDocument:
    doc = await db.scalar(select(UploadedDocument).where(UploadedDocument.id == upload_id,
                                                         UploadedDocument.case_id == case.id))
    if doc is None:
        raise NotFoundError("Document not found.")
    return doc


@router.post("/cases/{case_id}/uploads", status_code=201)
async def upload_document(case_id: uuid.UUID, background: BackgroundTasks, file: UploadFile = File(...),
                          ctx: RequestContext = Depends(get_context), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    case = await get_owned_case(db, case_id, ctx.user)
    await db.refresh(ctx.user, attribute_names=["preferences"])
    if not (ctx.user.preferences and ctx.user.preferences.consent_document_storage):
        raise AppError("Please allow document storage in Settings → Privacy before uploading.",
                       code="consent_required")
    count = await db.scalar(select(func.count()).select_from(UploadedDocument).where(UploadedDocument.case_id == case.id))
    if (count or 0) >= 50:
        raise AppError("A case can have at most 50 uploaded documents.", code="too_many_uploads")
    # Read in chunks and stop as soon as the limit is exceeded (never buffer an oversized body).
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    buf = bytearray()
    while chunk := await file.read(1024 * 1024):
        buf.extend(chunk)
        if len(buf) > max_bytes:
            raise AppError(f"The file is larger than {get_settings().max_upload_mb} MB.", code="too_large")
    data = bytes(buf)
    try:
        checked = validate_upload(file.filename or "document", data)
    except UploadRejected as exc:
        await record_audit(db, action="document.upload_rejected", actor_user_id=ctx.user.id, case_id=case.id,
                           ip_hash=ctx.ip_hash, outcome="failure", meta={"reason": exc.code})
        await db.commit()
        raise AppError(str(exc), code=exc.code) from exc
    key = await store_encrypted(f"cases/{case.id}", data)
    doc = UploadedDocument(case_id=case.id, user_id=ctx.user.id, original_filename=checked.safe_name,
                           content_type=checked.content_type, size_bytes=len(data), sha256=sha256_hex(data),
                           storage_key=key, status=DocumentStatus.UPLOADED, security_flags=checked.flags)
    db.add(doc)
    await db.flush()
    job = await create_job(db, "process_document", {"document_id": str(doc.id)})
    await record_audit(db, action="document.upload", actor_user_id=ctx.user.id, resource_type="uploaded_document",
                       resource_id=doc.id, case_id=case.id, ip_hash=ctx.ip_hash,
                       meta={"type": checked.content_type, "size": len(data)})
    await db.refresh(doc, attribute_names=["extraction"])
    body = ser.upload(doc)
    await db.commit()  # the job runs in its own session; nothing in this request touches the DB after this
    await dispatch(job, background)
    return body


@router.get("/cases/{case_id}/uploads")
async def list_uploads(case_id: uuid.UUID, ctx: RequestContext = Depends(get_context),
                       db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
    case = await get_owned_case(db, case_id, ctx.user)
    rows = (await db.scalars(select(UploadedDocument).where(UploadedDocument.case_id == case.id)
                             .order_by(UploadedDocument.created_at.desc()))).all()
    return [ser.upload(d) for d in rows]


@router.get("/cases/{case_id}/uploads/{upload_id}")
async def get_upload(case_id: uuid.UUID, upload_id: uuid.UUID, ctx: RequestContext = Depends(get_context),
                     db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    case = await get_owned_case(db, case_id, ctx.user)
    return ser.upload(await _owned_upload(db, case, upload_id), include_text=True)


@router.get("/cases/{case_id}/uploads/{upload_id}/file")
async def download_upload(case_id: uuid.UUID, upload_id: uuid.UUID, ctx: RequestContext = Depends(get_context),
                          db: AsyncSession = Depends(get_db)) -> Response:
    case = await get_owned_case(db, case_id, ctx.user)
    doc = await _owned_upload(db, case, upload_id)
    data = await load_decrypted(doc.storage_key)
    await record_audit(db, action="document.download", actor_user_id=ctx.user.id, resource_type="uploaded_document",
                       resource_id=doc.id, case_id=case.id, ip_hash=ctx.ip_hash)
    return Response(data, media_type=doc.content_type, headers={
        "Content-Disposition": f'attachment; filename="{doc.original_filename}"',
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
    })


@router.delete("/cases/{case_id}/uploads/{upload_id}")
async def delete_upload(case_id: uuid.UUID, upload_id: uuid.UUID, ctx: RequestContext = Depends(get_context),
                        db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    case = await get_owned_case(db, case_id, ctx.user)
    doc = await _owned_upload(db, case, upload_id)
    await get_storage().delete(doc.storage_key)
    await db.delete(doc)
    await record_audit(db, action="document.delete", actor_user_id=ctx.user.id, resource_type="uploaded_document",
                       resource_id=upload_id, case_id=case.id, ip_hash=ctx.ip_hash)
    return {"message": "Document deleted."}


@router.post("/cases/{case_id}/uploads/{upload_id}/accept-fields")
async def accept_fields(case_id: uuid.UUID, upload_id: uuid.UUID, payload: AcceptFields,
                        ctx: RequestContext = Depends(get_context), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Human review step: the user accepts specific extracted values as document-sourced facts."""
    case = await get_owned_case(db, case_id, ctx.user)
    doc = await _owned_upload(db, case, upload_id)
    if doc.extraction is None:
        raise AppError("This document has not been processed yet.", code="not_processed")
    created = []
    for name in payload.fields:
        if name not in FIELD_TO_FACT or name not in (doc.extraction.fields or {}):
            continue
        item = doc.extraction.fields[name]
        key = FIELD_TO_FACT[name]
        fact = await fact_service.upsert_fact(
            db, case.id, key, str(item["value"]), FactProvenance.DOCUMENT_EXTRACTED,
            value_type=SLOT_BY_KEY[key].value_type, excerpt=item.get("excerpt"), source_type="uploaded_document",
            source_id=str(doc.id), confidence=0.7)
        if fact:
            created.append(ser.fact(fact))
    doc.extraction.reviewed_at = utcnow()
    await fact_service.sync_case_columns(db, case)
    await record_audit(db, action="document.fields_accepted", actor_user_id=ctx.user.id,
                       resource_type="uploaded_document", resource_id=doc.id, case_id=case.id, ip_hash=ctx.ip_hash,
                       meta={"fields": payload.fields})
    return {"facts": created}


async def _next_label(db: AsyncSession, case_id: uuid.UUID) -> tuple[str, int]:
    count = await db.scalar(select(func.count()).select_from(EvidenceItem).where(EvidenceItem.case_id == case_id)) or 0
    return f"Annexure A-{count + 1}", count


@router.get("/cases/{case_id}/evidence")
async def list_evidence(case_id: uuid.UUID, ctx: RequestContext = Depends(get_context),
                        db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
    case = await get_owned_case(db, case_id, ctx.user)
    rows = (await db.scalars(select(EvidenceItem).where(EvidenceItem.case_id == case.id)
                             .order_by(EvidenceItem.order_index))).all()
    return [ser.evidence(e) for e in rows]


@router.post("/cases/{case_id}/evidence", status_code=201)
async def add_evidence(case_id: uuid.UUID, payload: EvidenceIn, ctx: RequestContext = Depends(get_context),
                       db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    case = await get_owned_case(db, case_id, ctx.user)
    if payload.document_id:
        await _owned_upload(db, case, payload.document_id)
    label, order = await _next_label(db, case.id)
    item = EvidenceItem(case_id=case.id, document_id=payload.document_id, label=label, title=payload.title,
                        description=payload.description, evidence_type=payload.evidence_type,
                        evidence_date=payload.evidence_date, order_index=order, confirmed_by_user=True)
    db.add(item)
    await db.flush()
    await record_audit(db, action="evidence.add", actor_user_id=ctx.user.id, resource_type="evidence_item",
                       resource_id=item.id, case_id=case.id, ip_hash=ctx.ip_hash)
    return ser.evidence(item)


@router.patch("/cases/{case_id}/evidence/{evidence_id}")
async def patch_evidence(case_id: uuid.UUID, evidence_id: uuid.UUID, payload: EvidencePatch,
                         ctx: RequestContext = Depends(get_context), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    case = await get_owned_case(db, case_id, ctx.user)
    item = await db.scalar(select(EvidenceItem).where(EvidenceItem.id == evidence_id, EvidenceItem.case_id == case.id))
    if item is None:
        raise NotFoundError("Evidence item not found.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    return ser.evidence(item)


@router.delete("/cases/{case_id}/evidence/{evidence_id}")
async def delete_evidence(case_id: uuid.UUID, evidence_id: uuid.UUID, ctx: RequestContext = Depends(get_context),
                          db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    case = await get_owned_case(db, case_id, ctx.user)
    item = await db.scalar(select(EvidenceItem).where(EvidenceItem.id == evidence_id, EvidenceItem.case_id == case.id))
    if item is None:
        raise NotFoundError("Evidence item not found.")
    await db.delete(item)
    await db.flush()
    # Re-label so annexure numbers stay continuous.
    rows = (await db.scalars(select(EvidenceItem).where(EvidenceItem.case_id == case.id)
                             .order_by(EvidenceItem.order_index))).all()
    for i, e in enumerate(rows):
        e.order_index = i
        e.label = f"Annexure A-{i + 1}"
    return {"message": "Removed from the evidence list."}
