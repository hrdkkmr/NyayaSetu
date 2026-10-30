from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import serializers as ser
from app.core.deps import RequestContext, get_context
from app.core.errors import NotFoundError
from app.db.session import get_db
from app.legal.retrieval import search
from app.models import LegalChunk, LegalDocument

router = APIRouter(prefix="/legal", tags=["legal"])


@router.get("/search")
async def legal_search(q: str = Query(min_length=2, max_length=500), domain: str | None = "consumer_protection",
                       limit: int = Query(default=6, ge=1, le=12), _: RequestContext = Depends(get_context),
                       db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    result = await search(db, q, legal_domain=domain, limit=limit)
    return result.as_dict()


def _doc(d: LegalDocument) -> dict[str, Any]:
    return {
        "key": d.key, "title": d.title, "doc_type": d.doc_type, "legal_domain": d.legal_domain,
        "jurisdiction": d.jurisdiction, "identifier": d.identifier, "source_url": d.source_url,
        "source_name": d.source.name if d.source else None, "publication_date": ser.iso(d.publication_date),
        "effective_date": ser.iso(d.effective_date), "effective_date_note": d.effective_date_note,
        "version_label": d.version_label, "amends": d.amends, "verification_status": d.verification_status,
        "verification_note": d.verification_note, "verified_at": ser.iso(d.verified_at),
        "retrieved_at": ser.iso(d.retrieved_at), "retrieval_method": d.retrieval_method,
        "sha256": d.sha256, "chunk_count": d.chunk_count, "ingestion_status": d.ingestion_status,
    }


@router.get("/sources")
async def legal_sources(_: RequestContext = Depends(get_context), db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
    docs = (await db.scalars(select(LegalDocument).order_by(LegalDocument.publication_date))).all()
    return [_doc(d) for d in docs]


@router.get("/chunks/{chunk_id}")
async def legal_chunk(chunk_id: uuid.UUID, _: RequestContext = Depends(get_context),
                      db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    chunk = await db.get(LegalChunk, chunk_id)
    if chunk is None:
        raise NotFoundError("Provision not found.")
    return {"id": str(chunk.id), "section_ref": chunk.section_ref, "chapter": chunk.chapter, "text": chunk.text,
            "document": _doc(chunk.document)}
