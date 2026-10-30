"""Hybrid legal retrieval: BM25 keyword + vector similarity, fused and reranked.

PostgreSQL uses pgvector (`<=>`) to pre-select vector candidates; SQLite computes
everything in Python. Both paths share the fusion, reranking, version notices and
confidence estimation so behaviour is identical across environments.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.legal.embeddings import cosine, get_embedder
from app.legal.text import expand_query, tokenize
from app.models import LegalChunk, LegalDocument

RRF_K = 60
_SECTION_IN_QUERY = re.compile(r"\b(?:section|sec\.?|s\.|धारा)\s*(\d{1,3}[A-Z]?)", re.IGNORECASE)
_RULE_IN_QUERY = re.compile(r"\b(?:rule|नियम)\s*(\d{1,3})", re.IGNORECASE)


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_key: str
    document_title: str
    document_type: str
    identifier: str | None
    section_ref: str | None
    chapter: str | None
    text: str
    source_url: str
    source_name: str
    jurisdiction: str
    publication_date: date | None
    effective_date: date | None
    effective_date_note: str | None
    version_label: str | None
    verification_status: str
    retrieved_at: datetime | None
    score: float
    keyword_score: float
    vector_score: float
    amendment_notices: list[str] = field(default_factory=list)

    def citation(self) -> str:
        parts = [self.section_ref, self.document_title]
        return ", ".join(p for p in parts if p)

    def as_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "document_key": self.document_key,
            "document_title": self.document_title,
            "document_type": self.document_type,
            "identifier": self.identifier,
            "section_ref": self.section_ref,
            "chapter": self.chapter,
            "text": self.text,
            "source_url": self.source_url,
            "source_name": self.source_name,
            "jurisdiction": self.jurisdiction,
            "publication_date": self.publication_date.isoformat() if self.publication_date else None,
            "effective_date": self.effective_date.isoformat() if self.effective_date else None,
            "effective_date_note": self.effective_date_note,
            "version_label": self.version_label,
            "verification_status": self.verification_status,
            "retrieved_at": self.retrieved_at.isoformat() if self.retrieved_at else None,
            "score": round(self.score, 4),
            "keyword_score": round(self.keyword_score, 4),
            "vector_score": round(self.vector_score, 4),
            "amendment_notices": self.amendment_notices,
            "citation": self.citation(),
        }


@dataclass
class RetrievalResult:
    query: str
    expanded_query: str
    glossary_terms: list[str]
    results: list[RetrievedChunk]
    confidence: str
    notes: list[str]
    embedder: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "expanded_query": self.expanded_query,
            "glossary_terms": self.glossary_terms,
            "confidence": self.confidence,
            "notes": self.notes,
            "embedder": self.embedder,
            "results": [r.as_dict() for r in self.results],
        }


def _bm25(query_tokens: list[str], docs: list[list[str]], k1: float = 1.4, b: float = 0.75) -> list[float]:
    n = len(docs)
    if n == 0 or not query_tokens:
        return [0.0] * n
    avgdl = sum(len(d) for d in docs) / n or 1.0
    df: Counter[str] = Counter()
    for d in docs:
        df.update(set(d))
    scores = []
    q_terms = Counter(query_tokens)
    for d in docs:
        tf = Counter(d)
        dl = len(d) or 1
        s = 0.0
        for term, qf in q_terms.items():
            if term not in tf:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            s += qf * idf * (tf[term] * (k1 + 1)) / (tf[term] + k1 * (1 - b + b * dl / avgdl))
        scores.append(s)
    return scores


def _defined_term(text: str) -> str | None:
    match = re.match(r"^\(\d{1,2}\)\s+[\"“]([^\"”]{2,60})[\"”]", text)
    return match.group(1).lower() if match else None


def _section_matches(ref: str | None, number: str, unit: str) -> bool:
    if not ref:
        return False
    return bool(re.fullmatch(rf"{unit} {re.escape(number)}(\(.*\))?", ref, re.IGNORECASE))


def _amendment_notices(doc: LegalDocument, section_ref: str | None, docs_by_key: dict[str, LegalDocument]) -> list[str]:
    notices: list[str] = []
    if not section_ref:
        return notices
    base = re.match(r"(Section|Rule) (\d+[A-Z]?)", section_ref)
    if not base:
        return notices
    for rel in doc.amends or []:
        provisions = rel.get("provisions") or []
        if any(p.startswith(f"{base.group(1)} {base.group(2)}(") or p == f"{base.group(1)} {base.group(2)}"
               for p in provisions):
            target = docs_by_key.get(rel.get("document", ""))
            if rel.get("effect"):
                notices.append(" ".join(str(rel["effect"]).split()))
            elif target is not None:
                notices.append(f"See also {target.title}, which relates to this provision.")
    return notices


async def search(
    db: AsyncSession,
    query: str,
    *,
    legal_domain: str | None = None,
    jurisdiction: str | None = None,
    doc_keys: list[str] | None = None,
    limit: int = 6,
) -> RetrievalResult:
    expanded, glossary = expand_query(query)
    notes: list[str] = []
    if glossary:
        notes.append("Hindi terms were matched to English legal terms to search the official English text.")

    stmt = (
        select(LegalChunk)
        .join(LegalDocument, LegalChunk.document_id == LegalDocument.id)
        .where(LegalDocument.ingestion_status.in_(["ingested", "unchanged"]))
        .options(selectinload(LegalChunk.document).selectinload(LegalDocument.source))
    )
    if legal_domain:
        stmt = stmt.where(LegalDocument.legal_domain == legal_domain)
    if jurisdiction:
        stmt = stmt.where(LegalDocument.jurisdiction.in_([jurisdiction, "IN"]))
    if doc_keys:
        stmt = stmt.where(LegalDocument.key.in_(doc_keys))

    embedder = get_embedder()
    qvec = (await embedder.embed([expanded]))[0]
    dialect = db.bind.dialect.name if db.bind else "sqlite"

    if dialect == "postgresql":
        vector_ids = list(
            (await db.scalars(stmt.order_by(LegalChunk.embedding.op("<=>")(qvec)).limit(60))).all()
        )
        q_tokens = tokenize(expanded)
        keyword_stmt = stmt
        if q_tokens:
            from sqlalchemy import or_

            keyword_stmt = stmt.where(or_(*[LegalChunk.search_text.contains(t) for t in q_tokens[:12]]))
        keyword_rows = list((await db.scalars(keyword_stmt.limit(400))).all())
        seen = {c.id for c in vector_ids}
        candidates = vector_ids + [c for c in keyword_rows if c.id not in seen]
    else:
        candidates = list((await db.scalars(stmt)).all())

    if not candidates:
        return RetrievalResult(query, expanded, glossary, [], "none",
                               ["No official legal sources are available for this topic yet."],
                               embedder.name)

    q_tokens = tokenize(expanded)
    doc_tokens = [c.search_text.split() for c in candidates]
    kw_scores = _bm25(q_tokens, doc_tokens)
    vec_scores = [cosine(qvec, c.embedding) if c.embedding else 0.0 for c in candidates]

    kw_rank = {i: r for r, i in enumerate(sorted(range(len(candidates)), key=lambda i: -kw_scores[i]))}
    vec_rank = {i: r for r, i in enumerate(sorted(range(len(candidates)), key=lambda i: -vec_scores[i]))}

    wanted_sections = _SECTION_IN_QUERY.findall(query)
    wanted_rules = _RULE_IN_QUERY.findall(query)
    asks_definition = bool(re.search(r"\b(what is|meaning|define|definition|matlab|क्या है|मतलब)\b", query, re.I))

    focus = re.search(r"(?:what is|what are|meaning of|define)\s+(?:a |an |the )?([a-z\-]+)", query, re.I)
    focus_term = focus.group(1).lower() if focus else None

    fused: list[tuple[float, int]] = []
    for i, chunk in enumerate(candidates):
        score = 1 / (RRF_K + kw_rank[i]) + 1 / (RRF_K + vec_rank[i])
        if kw_scores[i] == 0:
            score *= 0.6
        if any(_section_matches(chunk.section_ref, n, "Section") for n in wanted_sections):
            score += 0.05
        if any(_section_matches(chunk.section_ref, n, "Rule") for n in wanted_rules):
            score += 0.05
        if chunk.section_ref and chunk.section_ref.startswith("Section 2("):
            term = _defined_term(chunk.text)
            if term and re.search(rf"\b{re.escape(term)}\b", query, re.IGNORECASE):
                score += 0.02 if asks_definition else 0.008
                if focus_term and term.startswith(focus_term):
                    score += 0.01
            elif asks_definition:
                score *= 1.1
        if chunk.section_ref == "Preamble":
            score *= 0.5
        fused.append((score, i))
    fused.sort(reverse=True)

    docs_by_key = {c.document.key: c.document for c in candidates}
    results: list[RetrievedChunk] = []
    for score, i in fused[:limit]:
        chunk = candidates[i]
        doc = chunk.document
        results.append(
            RetrievedChunk(
                chunk_id=str(chunk.id),
                document_key=doc.key,
                document_title=doc.title,
                document_type=doc.doc_type,
                identifier=doc.identifier,
                section_ref=chunk.section_ref,
                chapter=chunk.chapter,
                text=chunk.text,
                source_url=doc.source_url,
                source_name=doc.source.name if doc.source else "",
                jurisdiction=doc.jurisdiction,
                publication_date=doc.publication_date,
                effective_date=doc.effective_date,
                effective_date_note=doc.effective_date_note,
                version_label=doc.version_label,
                verification_status=doc.verification_status,
                retrieved_at=doc.retrieved_at,
                score=score,
                keyword_score=kw_scores[i],
                vector_score=vec_scores[i],
                amendment_notices=_amendment_notices(doc, chunk.section_ref, docs_by_key),
            )
        )

    confidence = _confidence(q_tokens, results)
    if confidence == "low":
        notes.append("The match between your question and the available sources is weak.")
    if any(r.amendment_notices for r in results):
        notes.append("Some retrieved provisions were later changed by a separate notification.")
    return RetrievalResult(query, expanded, glossary, results, confidence, notes, embedder.name)


def _confidence(q_tokens: list[str], results: list[RetrievedChunk]) -> str:
    if not results:
        return "none"
    if not q_tokens:
        return "low"
    top = results[0]
    top_tokens = set(tokenize(f"{top.section_ref or ''} {top.text}"))
    coverage = len(set(q_tokens) & top_tokens) / len(set(q_tokens))
    if coverage >= 0.6 and top.keyword_score > 4:
        return "high"
    if coverage >= 0.35 and top.keyword_score > 1.5:
        return "medium"
    return "low"


async def get_chunks_by_ref(
    db: AsyncSession, document_key: str, section_refs: list[str]
) -> list[LegalChunk]:
    """Fetch specific provisions (used by deterministic domain rules for citations)."""
    stmt = (
        select(LegalChunk)
        .join(LegalDocument, LegalChunk.document_id == LegalDocument.id)
        .where(LegalDocument.key == document_key, LegalChunk.section_ref.in_(section_refs))
        .options(selectinload(LegalChunk.document).selectinload(LegalDocument.source))
        .order_by(LegalChunk.ordinal)
    )
    return list((await db.scalars(stmt)).all())
