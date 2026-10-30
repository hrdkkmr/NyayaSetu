"""Ingestion pipeline: official source → text → normalised chunks → embeddings → database.

Each document is read from its local snapshot (downloaded from the official URL
recorded in the manifest). With LEGAL_FETCH_LIVE=true the official URL is fetched
first; if the bytes differ from the snapshot the document is flagged so a reviewer
can check whether the law changed.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import yaml
from pypdf import PdfReader
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.security import sha256_hex
from app.db.base import utcnow
from app.legal.chunking import chunk_statute, normalise
from app.legal.embeddings import get_embedder
from app.legal.text import search_text
from app.models import LegalChunk, LegalDocument, LegalSource
from app.models.enums import VerificationStatus

logger = logging.getLogger(__name__)


@dataclass
class IngestionReport:
    document_key: str
    status: str
    chunks: int = 0
    detail: str | None = None


def load_manifest(path: str | None = None) -> dict[str, Any]:
    manifest_path = Path(path or get_settings().legal_manifest_path)
    with manifest_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    data["_base_dir"] = manifest_path.parent
    return data


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def extract_pdf_text(data: bytes) -> tuple[str, int]:
    reader = PdfReader(io.BytesIO(data))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages), len(pages)


async def _fetch_live(url: str) -> bytes | None:
    try:
        async with httpx.AsyncClient(
            timeout=60, follow_redirects=True, headers={"User-Agent": "NyayaSetu-ingest/0.1"}
        ) as client:
            resp = await client.get(url)
            if resp.status_code == 200 and resp.content.startswith(b"%PDF"):
                return resp.content
            logger.warning("Live fetch of %s returned %s", url, resp.status_code)
    except httpx.HTTPError as exc:
        logger.warning("Live fetch of %s failed: %s", url, exc)
    return None


async def ensure_sources(db: AsyncSession, manifest: dict[str, Any]) -> dict[str, LegalSource]:
    sources: dict[str, LegalSource] = {}
    for entry in manifest.get("sources", []):
        source = await db.scalar(select(LegalSource).where(LegalSource.key == entry["key"]))
        if source is None:
            source = LegalSource(key=entry["key"])
            db.add(source)
        source.name = entry["name"]
        source.base_url = entry["base_url"]
        source.source_type = entry["source_type"]
        sources[entry["key"]] = source
    await db.flush()
    return sources


async def ingest_document(
    db: AsyncSession,
    entry: dict[str, Any],
    sources: dict[str, LegalSource],
    base_dir: Path,
    *,
    fetch_live: bool = False,
    force: bool = False,
) -> IngestionReport:
    key = entry["key"]
    doc = await db.scalar(select(LegalDocument).where(LegalDocument.key == key))
    if doc is None:
        doc = LegalDocument(key=key, source_id=sources[entry["source"]].id)
        db.add(doc)
    doc.source_id = sources[entry["source"]].id
    doc.title = " ".join(str(entry["title"]).split())
    doc.doc_type = entry["doc_type"]
    doc.legal_domain = entry["legal_domain"]
    doc.jurisdiction = entry.get("jurisdiction", "IN")
    doc.source_url = entry["source_url"]
    doc.publication_date = _parse_date(entry.get("publication_date"))
    doc.effective_date = _parse_date(entry.get("effective_date"))
    doc.effective_date_note = " ".join(str(entry.get("effective_date_note") or "").split()) or None
    doc.identifier = entry.get("identifier")
    doc.version_label = entry.get("version_label")
    doc.amends = entry.get("amends") or entry.get("amended_by") or []
    doc.language = entry.get("language", "en")

    snapshot_path = base_dir / entry["snapshot"]
    data: bytes | None = None
    method = "snapshot"
    note: str | None = None
    if fetch_live:
        live = await _fetch_live(entry["source_url"])
        if live is not None:
            data, method = live, "live_fetch"
            if snapshot_path.exists() and sha256_hex(snapshot_path.read_bytes()) != sha256_hex(live):
                note = (
                    "Official source bytes differ from the stored snapshot. A reviewer must "
                    "check whether the document was amended or re-issued."
                )
    if data is None:
        if not snapshot_path.exists():
            doc.ingestion_status = "failed"
            doc.ingestion_error = "Snapshot missing and live fetch unavailable"
            return IngestionReport(key, "failed", detail=doc.ingestion_error)
        data = snapshot_path.read_bytes()

    digest = sha256_hex(data)
    if doc.sha256 == digest and doc.chunk_count > 0 and not force:
        doc.ingestion_status = "unchanged"
        return IngestionReport(key, "unchanged", doc.chunk_count)

    try:
        raw_text, _pages = extract_pdf_text(data)
    except Exception as exc:  # noqa: BLE001 - malformed PDF of any kind
        doc.ingestion_status = "failed"
        doc.ingestion_error = f"Text extraction failed: {exc}"
        return IngestionReport(key, "failed", detail=doc.ingestion_error)

    text = normalise(raw_text)
    unit = "Section" if entry["doc_type"] == "act" else "Rule"
    chunks = chunk_statute(text, unit_label=unit)
    if not chunks:
        doc.ingestion_status = "failed"
        doc.ingestion_error = "No text could be extracted (scanned document needs OCR)"
        return IngestionReport(key, "failed", detail=doc.ingestion_error)

    embedder = get_embedder()
    vectors = await embedder.embed([f"{c.section_ref or ''} {c.text}" for c in chunks])

    await db.flush()
    await db.execute(delete(LegalChunk).where(LegalChunk.document_id == doc.id))
    for chunk, vector in zip(chunks, vectors, strict=True):
        db.add(
            LegalChunk(
                document_id=doc.id,
                ordinal=chunk.ordinal,
                section_ref=chunk.section_ref,
                heading=chunk.heading,
                chapter=chunk.chapter,
                text=chunk.text,
                search_text=search_text(f"{chunk.section_ref or ''} {chunk.text}"),
                token_count=len(chunk.text.split()),
                embedding=vector,
                embedding_model=embedder.name,
            )
        )
    doc.sha256 = digest
    doc.retrieved_at = utcnow()
    doc.retrieval_method = method
    doc.chunk_count = len(chunks)
    doc.ingestion_status = "ingested"
    doc.ingestion_error = None
    # Text came from an official publisher; it has not been checked for later amendments
    # unless a reviewer marks it verified.
    if note:
        doc.verification_status = VerificationStatus.STALE
        doc.verification_note = note
    elif doc.verification_status != VerificationStatus.VERIFIED_BY_REVIEWER:
        doc.verification_status = VerificationStatus.FETCHED_OFFICIAL
        doc.verification_note = (
            f"Text taken from the official publication ({method}). Not yet confirmed by a "
            "reviewer to be the current consolidated version."
        )
    return IngestionReport(key, "ingested", len(chunks), note)


async def ingest_all(
    db: AsyncSession, *, fetch_live: bool | None = None, force: bool = False,
    manifest_path: str | None = None,
) -> list[IngestionReport]:
    manifest = load_manifest(manifest_path)
    live = get_settings().legal_fetch_live if fetch_live is None else fetch_live
    sources = await ensure_sources(db, manifest)
    reports = []
    for entry in manifest.get("documents", []):
        report = await ingest_document(
            db, entry, sources, manifest["_base_dir"], fetch_live=live, force=force
        )
        logger.info("Ingestion %s: %s (%s chunks)", report.document_key, report.status, report.chunks)
        reports.append(report)
    await db.flush()
    return reports
