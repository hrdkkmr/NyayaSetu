"""Generated-document service: create, version, edit and verify drafts."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.verification import verify_document
from app.core.errors import AppError, NotFoundError
from app.documents.templates import BUILDERS, DOC_TYPES, TEMPLATE_VERSION, DraftContext
from app.models import DocumentVersion, EvidenceItem, GeneratedDocument
from app.models.enums import GeneratedDocStatus
from app.services.facts import active_facts, load_slots


def content_hash(content: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


async def evidence_list(db: AsyncSession, case_id: uuid.UUID) -> list[dict[str, Any]]:
    items = await db.scalars(
        select(EvidenceItem).where(EvidenceItem.case_id == case_id).order_by(EvidenceItem.order_index)
    )
    return [
        {"id": str(e.id), "label": e.label, "title": e.title, "description": e.description,
         "evidence_date": e.evidence_date.isoformat() if e.evidence_date else None,
         "document_id": str(e.document_id) if e.document_id else None}
        for e in items.all()
    ]


async def facts_for_verification(db: AsyncSession, case_id: uuid.UUID) -> list[dict[str, Any]]:
    return [{"key": f.key, "value": f.value, "provenance": f.provenance, "id": str(f.id)}
            for f in await active_facts(db, case_id)]


def _trace(content: dict[str, Any], outcomes: dict[str, Any]) -> dict[str, Any]:
    fact_ids: set[str] = set()
    refs: set[str] = set()
    for block in content.get("blocks", []):
        fact_ids.update(block.get("sources", {}).get("facts", []))
        refs.update(block.get("sources", {}).get("refs", []))
    return {
        "fact_ids": sorted(fact_ids),
        "legal_refs": sorted(refs),
        "rule_outcomes": {k: {"value": v.get("value"), "grounded": v.get("grounded")} for k, v in outcomes.items()},
        "template": TEMPLATE_VERSION,
    }


async def generate_documents(
    db: AsyncSession, case_id: uuid.UUID, outcomes: dict[str, Any], citations: list[dict[str, Any]],
    today: date, doc_types: list[str] | None = None,
) -> list[dict[str, Any]]:
    slots = await load_slots(db, case_id)
    evidence = await evidence_list(db, case_id)
    ctx = DraftContext(slots={k: dict(v) for k, v in slots.items()}, outcomes=outcomes, evidence=evidence, citations=citations, today=today)
    facts = await facts_for_verification(db, case_id)
    results = []
    for doc_type in doc_types or list(BUILDERS):
        content = BUILDERS[doc_type](ctx)
        doc = await db.scalar(
            select(GeneratedDocument)
            .where(GeneratedDocument.case_id == case_id, GeneratedDocument.doc_type == doc_type)
            .options(selectinload(GeneratedDocument.versions))
        )
        if doc is None:
            doc = GeneratedDocument(case_id=case_id, doc_type=doc_type, title=DOC_TYPES[doc_type],
                                    template_id=f"consumer.{doc_type}", template_version=TEMPLATE_VERSION,
                                    current_version=0, versions=[])
            db.add(doc)
            await db.flush()
        digest = content_hash(content)
        latest = doc.versions[-1] if doc.versions else None
        validation = verify_document(content, facts=facts, outcomes=outcomes, evidence=evidence, today=today)
        if latest is not None and latest.content_sha256 == digest:
            latest.validation = validation
            results.append({"document_id": str(doc.id), "doc_type": doc_type, "version": latest.version_number,
                            "changed": False, "validation": validation})
            continue
        version = DocumentVersion(
            generated_document_id=doc.id, version_number=doc.current_version + 1, content=content,
            content_sha256=digest, created_by="document_agent", change_note="Generated from confirmed case facts",
            source_trace=_trace(content, outcomes), validation=validation,
        )
        db.add(version)
        doc.current_version = version.version_number
        doc.status = GeneratedDocStatus.DRAFT
        doc.template_version = TEMPLATE_VERSION
        await db.flush()
        results.append({"document_id": str(doc.id), "doc_type": doc_type, "version": version.version_number,
                        "changed": True, "validation": validation})
    return results


async def get_document(db: AsyncSession, case_id: uuid.UUID, document_id: uuid.UUID) -> GeneratedDocument:
    doc = await db.scalar(
        select(GeneratedDocument)
        .where(GeneratedDocument.id == document_id, GeneratedDocument.case_id == case_id)
        .options(selectinload(GeneratedDocument.versions))
    )
    if doc is None:
        raise NotFoundError("Document not found.")
    return doc


def current_version(doc: GeneratedDocument) -> DocumentVersion:
    for v in doc.versions:
        if v.version_number == doc.current_version:
            return v
    raise NotFoundError("Document version not found.")


async def edit_document(
    db: AsyncSession, case_id: uuid.UUID, document_id: uuid.UUID, edits: dict[str, str],
    note: str | None, outcomes: dict[str, Any], today: date,
) -> DocumentVersion:
    """Apply user edits to editable text blocks, creating a new version."""
    doc = await get_document(db, case_id, document_id)
    base = current_version(doc)
    content = json.loads(json.dumps(base.content))
    editable = {b["id"]: b for b in content.get("blocks", []) if b.get("editable")}
    unknown = [k for k in edits if k not in editable]
    if unknown:
        raise AppError("Some sections cannot be edited.", code="not_editable", details=unknown)
    changed = False
    for block_id, text in edits.items():
        text = text.strip()
        if len(text) > 8000:
            raise AppError("A section is too long.", code="too_long", details=[block_id])
        block = editable[block_id]
        block_changed = False
        if block["type"] == "list":
            items = [line.strip() for line in text.splitlines() if line.strip()]
            if items != block["items"]:
                block["items"] = items
                block_changed = True
        elif text != block["text"]:
            block["text"] = text
            block_changed = True
        if block_changed:
            block.setdefault("sources", {})["edited_by_user"] = True
            changed = True
    if not changed:
        return base
    evidence = await evidence_list(db, case_id)
    facts = await facts_for_verification(db, case_id)
    version = DocumentVersion(
        generated_document_id=doc.id, version_number=doc.current_version + 1, content=content,
        content_sha256=content_hash(content), created_by="user", change_note=(note or "Edited by user")[:500],
        source_trace={**(base.source_trace or {}), "edited_from_version": base.version_number},
        validation=verify_document(content, facts=facts, outcomes=outcomes, evidence=evidence, today=today),
    )
    db.add(version)
    doc.current_version = version.version_number
    doc.status = GeneratedDocStatus.DRAFT
    await db.flush()
    await db.refresh(doc, attribute_names=["versions"])
    return version
