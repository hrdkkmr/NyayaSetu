"""Background job handlers."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import evidence
from app.agents.llm import get_llm
from app.core.audit import record_audit
from app.legal.ingestion import ingest_all
from app.models import DocumentExtraction, UploadedDocument, UserPreferences
from app.models.enums import DocumentStatus
from app.services.document_processing import extract_document
from app.services.jobs import handler
from app.services.notifications import notify, send_deadline_reminders
from app.services.storage import load_decrypted


@handler("process_document")
async def process_document(db: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
    doc = await db.get(UploadedDocument, uuid.UUID(payload["document_id"]))
    if doc is None:
        return {"skipped": "document deleted"}
    doc.status = DocumentStatus.PROCESSING
    await db.flush()
    try:
        data = await load_decrypted(doc.storage_key)
        result = extract_document(doc.content_type, data)
    except Exception as exc:
        doc.status = DocumentStatus.FAILED
        doc.error = f"Could not read this document ({type(exc).__name__})."
        raise
    ai_fields: dict[str, Any] = {}
    prefs = await db.get(UserPreferences, doc.user_id)
    llm = get_llm()
    if result.text and prefs is not None and prefs.consent_external_ai and llm.available:
        ai_fields = await evidence.extract_with_llm(llm, result.text)
    result.fields = evidence.merge_fields(result.fields, ai_fields)
    extraction = doc.extraction or DocumentExtraction(document_id=doc.id)
    extraction.method = result.method
    extraction.text = result.text
    extraction.language_hint = result.language_hint
    extraction.fields = result.fields
    extraction.injection_flags = result.injection_flags
    if doc.extraction is None:
        db.add(extraction)
    doc.page_count = result.page_count
    doc.document_class = result.document_class
    doc.status = DocumentStatus.NEEDS_OCR if result.needs_ocr else DocumentStatus.PROCESSED
    flags = set(doc.security_flags or [])
    if result.injection_flags:
        flags.add("contains_ai_instructions")
    doc.security_flags = sorted(flags)
    await notify(db, doc.user_id, "document_processed",
                 f"“{doc.original_filename}” is ready to review" if not result.needs_ocr
                 else f"“{doc.original_filename}” needs OCR to read its text",
                 case_id=doc.case_id, link=f"/cases/{doc.case_id}/documents")
    await record_audit(db, action="document.processed", actor_user_id=None, actor_type="system",
                       resource_type="uploaded_document", resource_id=doc.id, case_id=doc.case_id,
                       meta={"method": result.method, "fields": sorted(result.fields), "ai_fields": sorted(ai_fields),
                             "injection_flags": len(result.injection_flags)})
    return {"method": result.method, "fields": sorted(result.fields), "needs_ocr": result.needs_ocr}


@handler("ingest_legal_sources")
async def ingest_legal(db: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
    reports = await ingest_all(db, fetch_live=payload.get("fetch_live"), force=payload.get("force", False))
    return {"documents": [r.__dict__ for r in reports]}


@handler("deadline_reminders")
async def deadline_reminders(db: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
    return await send_deadline_reminders(db)


@handler("integration_health")
async def integration_health(db: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
    from app.services.health import check_integrations

    return {"integrations": await check_integrations(db)}
