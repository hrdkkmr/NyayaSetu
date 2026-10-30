"""Case fact store with provenance rules.

* A new value from the same provenance class supersedes the older value (the user
  corrected themselves, or a document was re-processed).
* Values from different classes coexist, so a conflict between what the user said
  and what a document shows is visible to the verification agent instead of being
  silently overwritten.
* AI inferences are never promoted automatically; only the user can confirm them.
"""

from __future__ import annotations

import re
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.state import SlotValue
from app.db.base import utcnow
from app.models import Case, CaseFact
from app.models.enums import FactProvenance, FactStatus

# Priority when several active facts exist for one key (higher wins for display).
PROVENANCE_RANK = {
    FactProvenance.USER_CONFIRMED: 4,
    FactProvenance.USER_STATED: 3,
    FactProvenance.DOCUMENT_EXTRACTED: 2,
    FactProvenance.AI_INFERENCE: 1,
}
_CLASS = {
    FactProvenance.USER_CONFIRMED: "user",
    FactProvenance.USER_STATED: "user",
    FactProvenance.DOCUMENT_EXTRACTED: "document",
    FactProvenance.AI_INFERENCE: "ai",
}


async def active_facts(db: AsyncSession, case_id: uuid.UUID) -> list[CaseFact]:
    rows = await db.scalars(
        select(CaseFact)
        .where(CaseFact.case_id == case_id, CaseFact.status == FactStatus.ACTIVE)
        .order_by(CaseFact.created_at)
    )
    return list(rows.all())


def best_by_key(facts: list[CaseFact]) -> dict[str, CaseFact]:
    best: dict[str, CaseFact] = {}
    for fact in facts:
        current = best.get(fact.key)
        rank = PROVENANCE_RANK.get(FactProvenance(fact.provenance), 0)
        if current is None or rank >= PROVENANCE_RANK.get(FactProvenance(current.provenance), 0):
            best[fact.key] = fact
    return best


async def load_slots(db: AsyncSession, case_id: uuid.UUID) -> dict[str, SlotValue]:
    best = best_by_key(await active_facts(db, case_id))
    return {
        key: SlotValue(
            fact_id=str(f.id),
            value=f.value,
            provenance=f.provenance,
            excerpt=f.source_excerpt,
            confirmed=f.provenance in (FactProvenance.USER_CONFIRMED, FactProvenance.USER_STATED),
        )
        for key, f in best.items()
    }


async def upsert_fact(
    db: AsyncSession,
    case_id: uuid.UUID,
    key: str,
    value: str,
    provenance: FactProvenance,
    *,
    value_type: str = "text",
    excerpt: str | None = None,
    source_type: str | None = None,
    source_id: str | None = None,
    confidence: float | None = None,
) -> CaseFact | None:
    value = value.strip()
    if not value:
        return None
    existing = [f for f in await active_facts(db, case_id) if f.key == key]
    for fact in existing:
        same_class = _CLASS[FactProvenance(fact.provenance)] == _CLASS[provenance]
        if fact.value.strip().lower() == value.lower() and (same_class or provenance == FactProvenance.USER_CONFIRMED):
            # Same value from the same kind of source (or the user confirming it): upgrade, don't duplicate.
            # A matching value from a *different* source is kept as its own record (corroboration).
            if PROVENANCE_RANK[provenance] > PROVENANCE_RANK[FactProvenance(fact.provenance)]:
                fact.provenance = provenance
                fact.source_excerpt = excerpt or fact.source_excerpt
                if provenance == FactProvenance.USER_CONFIRMED:
                    fact.confirmed_at = utcnow()
            return fact
    for fact in existing:
        if _CLASS[FactProvenance(fact.provenance)] == _CLASS[provenance]:
            fact.status = FactStatus.SUPERSEDED
    fact = CaseFact(
        case_id=case_id, key=key, value=value[:4000], value_type=value_type, provenance=provenance,
        source_excerpt=(excerpt or "")[:1000] or None, source_type=source_type, source_id=source_id,
        confidence=confidence,
        confirmed_at=utcnow() if provenance == FactProvenance.USER_CONFIRMED else None,
    )
    db.add(fact)
    await db.flush()
    return fact


def parse_money(value: str | None) -> Decimal | None:
    if not value:
        return None
    try:
        return Decimal(re.sub(r"[^\d.]", "", value))
    except (InvalidOperation, ValueError):
        return None


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


async def sync_case_columns(db: AsyncSession, case: Case) -> None:
    """Mirror key facts onto the case row for listing, filtering and deadlines."""
    best = best_by_key(await active_facts(db, case.id))

    def val(key: str) -> str | None:
        return best[key].value if key in best else None

    case.financial_amount = parse_money(val("amount_paid"))
    case.incident_date = parse_date(val("problem_date")) or parse_date(val("purchase_date"))
    if val("grievance"):
        case.incident_summary = val("grievance")
    loc = val("complainant_location")
    if loc:
        parts = [p.strip() for p in re.split(r",|\bin\b|में", loc) if p.strip()]
        case.location_district = parts[0][:80] if parts else None
        case.location_state = parts[-1][:80] if len(parts) > 1 else case.location_state
    product = val("product_or_service")
    seller = val("seller_name")
    if case.title.startswith(("New case", "नया मामला")) and (product or seller):
        title = " — ".join(x for x in [product, seller] if x)
        case.title = title[:200]
