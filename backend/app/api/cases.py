from __future__ import annotations

import secrets
import uuid
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import STAGES, run_case_workflow
from app.agents.safety import sanitize_user_text
from app.api import serializers as ser
from app.core.audit import record_audit
from app.core.deps import RequestContext, get_context, get_owned_case
from app.core.errors import AppError, NotFoundError
from app.db.base import utcnow
from app.db.session import get_db
from app.domains.consumer.slots import SLOT_BY_KEY, SLOTS
from app.models import (
    AgentExecution,
    Approval,
    AuditLog,
    Case,
    CaseFact,
    CaseUpdate,
    Conversation,
    ConversationMessage,
    Deadline,
    FilingRecord,
    GeneratedDocument,
    LegalChunk,
    LegalCitation,
    Notification,
    UploadedDocument,
    WorkflowInstance,
    WorkflowStep,
)
from app.models.enums import (
    CaseStatus,
    DeadlineKind,
    DeadlineStatus,
    FactProvenance,
    FactStatus,
    MessageRole,
    StepStatus,
    UpdateSource,
)
from app.services import facts as fact_service
from app.services.calendar import build_ics

router = APIRouter(tags=["cases"])


class CaseCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    language: Literal["en", "hi"] = "en"
    description: str | None = Field(default=None, max_length=4000)
    modality: Literal["text", "voice"] = "text"


class CaseUpdateIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    modality: Literal["text", "voice"] = "text"
    language: Literal["en", "hi"] | None = None


class FactIn(BaseModel):
    key: str = Field(max_length=80)
    value: str = Field(min_length=1, max_length=4000)


class DeadlineIn(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    due_date: date
    kind: Literal["hearing", "response", "user", "legal_notice"] = "user"
    reminder_days_before: int = Field(default=3, ge=0, le=60)


class DeadlinePatch(BaseModel):
    status: Literal["open", "done", "dismissed"]


class UpdateIn(BaseModel):
    update_type: Literal["hearing", "notice", "status", "note", "order"]
    title: str = Field(min_length=2, max_length=300)
    body: str | None = Field(default=None, max_length=4000)
    event_date: date | None = None


def _reference() -> str:
    return f"NS-{date.today().year}-{secrets.token_hex(3).upper()}"


async def _conversation(db: AsyncSession, case: Case, ctx: RequestContext) -> Conversation:
    conv = await db.scalar(select(Conversation).where(Conversation.case_id == case.id).order_by(Conversation.created_at))
    if conv is None:
        await db.refresh(ctx.user, attribute_names=["preferences"])
        conv = Conversation(user_id=ctx.user.id, case_id=case.id, title=case.title, language=case.language,
                            store_transcript=bool(ctx.user.preferences and ctx.user.preferences.consent_store_transcripts))
        db.add(conv)
        await db.flush()
    return conv


async def post_message(db: AsyncSession, case: Case, ctx: RequestContext, text: str, modality: str,
                       language: str | None) -> dict[str, Any]:
    """Store the user's message, run the workflow, store the reply. Shared by REST and voice."""
    text = sanitize_user_text(text)
    if language:
        case.language = language
    conv = await _conversation(db, case, ctx)
    await db.refresh(ctx.user, attribute_names=["preferences"])
    store = bool(ctx.user.preferences and ctx.user.preferences.consent_store_transcripts)
    conv.store_transcript = store
    user_msg = ConversationMessage(conversation_id=conv.id, role=MessageRole.USER,
                                   content=text if store else "[not stored — transcript storage is off]",
                                   redacted=not store, language=language or case.language, modality=modality)
    db.add(user_msg)
    await db.flush()
    result = await run_case_workflow(db, case, ctx.user, "message", message=text, message_id=str(user_msg.id),
                                     modality=modality)
    reply = result.reply or ""
    bot_msg = ConversationMessage(conversation_id=conv.id, role=MessageRole.ASSISTANT,
                                  content=reply if store else "[not stored — transcript storage is off]",
                                  redacted=not store, language=result.language, modality=modality,
                                  meta={"cards": result.cards if store else [], "phase": result.phase})
    db.add(bot_msg)
    await db.flush()
    return {
        "user_message": {**ser.message(user_msg), "content": text},
        "assistant_message": {**ser.message(bot_msg), "content": reply, "cards": result.cards},
        "phase": result.phase, "asked_slot": result.asked_slot, "language": result.language,
        "case": ser.case_summary(case), "errors": result.errors,
        "trace": result.trace, "ai_status": result.ai_status,
    }


@router.get("/dashboard")
async def dashboard(ctx: RequestContext = Depends(get_context), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    uid = ctx.user.id
    cases = (await db.scalars(select(Case).where(Case.user_id == uid, Case.archived_at.is_(None))
                              .order_by(Case.updated_at.desc()).limit(20))).all()
    case_ids = [c.id for c in cases]
    deadlines = (await db.scalars(select(Deadline).where(Deadline.case_id.in_(case_ids),
                 Deadline.status == DeadlineStatus.OPEN).order_by(Deadline.due_date).limit(10))).all() if case_ids else []
    drafts_to_review = (await db.execute(
        select(GeneratedDocument, Case.title).join(Case, GeneratedDocument.case_id == Case.id)
        .where(Case.user_id == uid, GeneratedDocument.status == "draft", Case.archived_at.is_(None)))).all()
    pending_steps = (await db.execute(
        select(WorkflowStep, WorkflowInstance.case_id).join(WorkflowInstance, WorkflowStep.workflow_id == WorkflowInstance.id)
        .where(WorkflowInstance.case_id.in_(case_ids), WorkflowStep.status == StepStatus.IN_PROGRESS,
               WorkflowStep.owner == "user"))).all() if case_ids else []
    filings = (await db.scalars(select(FilingRecord).where(FilingRecord.case_id.in_(case_ids)))).all() if case_ids else []
    notes = (await db.scalars(select(Notification).where(Notification.user_id == uid)
                              .order_by(Notification.created_at.desc()).limit(8))).all()
    unread = await db.scalar(select(func.count()).select_from(Notification).where(
        Notification.user_id == uid, Notification.read_at.is_(None)))
    recent = (await db.execute(
        select(Conversation, Case.title).join(Case, Conversation.case_id == Case.id)
        .where(Conversation.user_id == uid).order_by(Conversation.updated_at.desc()).limit(5))).all()
    titles = {c.id: c.title for c in cases}
    return {
        "cases": [ser.case_summary(c) for c in cases],
        "deadlines": [{**ser.deadline(d), "case_id": str(d.case_id), "case_title": titles.get(d.case_id)} for d in deadlines],
        "documents_to_review": [{"id": str(d.id), "case_id": str(d.case_id), "title": d.title, "case_title": t}
                                for d, t in drafts_to_review],
        "pending_actions": [{**ser.step(s), "case_id": str(cid), "case_title": titles.get(cid)} for s, cid in pending_steps],
        "filings": [{**ser.filing(f), "case_id": str(f.case_id), "case_title": titles.get(f.case_id)} for f in filings],
        "notifications": [ser.notification(n) for n in notes],
        "unread_notifications": unread or 0,
        "recent_conversations": [{"id": str(c.id), "case_id": str(c.case_id), "case_title": t,
                                  "updated_at": ser.iso(c.updated_at)} for c, t in recent],
    }


@router.get("/cases")
async def list_cases(include_archived: bool = False, status: str | None = None,
                     ctx: RequestContext = Depends(get_context), db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
    stmt = select(Case).where(Case.user_id == ctx.user.id)
    if not include_archived:
        stmt = stmt.where(Case.archived_at.is_(None))
    if status:
        stmt = stmt.where(Case.status == status)
    return [ser.case_summary(c) for c in (await db.scalars(stmt.order_by(Case.updated_at.desc()))).all()]


@router.post("/cases", status_code=201)
async def create_case(payload: CaseCreate, ctx: RequestContext = Depends(get_context),
                      db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    title = (payload.title or "").strip() or ("नया मामला" if payload.language == "hi" else "New case")
    case = Case(user_id=ctx.user.id, reference=_reference(), title=title, language=payload.language,
                status=CaseStatus.INTAKE, analysis={})
    db.add(case)
    await db.flush()
    await record_audit(db, action="case.create", actor_user_id=ctx.user.id, resource_type="case",
                       resource_id=case.id, case_id=case.id, ip_hash=ctx.ip_hash)
    result: dict[str, Any] = {"case": ser.case_summary(case)}
    if payload.description:
        result["turn"] = await post_message(db, case, ctx, payload.description, payload.modality, payload.language)
        result["case"] = ser.case_summary(case)
    return result


@router.get("/cases/{case_id}")
async def get_case(case_id: uuid.UUID, ctx: RequestContext = Depends(get_context),
                   db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    case = await get_owned_case(db, case_id, ctx.user)
    facts = await fact_service.active_facts(db, case.id)
    best = fact_service.best_by_key(facts)
    workflow = await db.scalar(select(WorkflowInstance).where(WorkflowInstance.case_id == case.id))
    steps = (await db.scalars(select(WorkflowStep).where(WorkflowStep.workflow_id == workflow.id)
                              .order_by(WorkflowStep.order_index))).all() if workflow else []
    deadlines = (await db.scalars(select(Deadline).where(Deadline.case_id == case.id).order_by(Deadline.due_date))).all()
    counts = {
        "uploads": await db.scalar(select(func.count()).select_from(UploadedDocument).where(UploadedDocument.case_id == case.id)),
        "drafts": await db.scalar(select(func.count()).select_from(GeneratedDocument).where(GeneratedDocument.case_id == case.id)),
        "citations": await db.scalar(select(func.count()).select_from(LegalCitation).where(LegalCitation.case_id == case.id)),
    }
    from app.agents.intake import missing_required

    slots = await fact_service.load_slots(db, case.id)
    state = (workflow.state if workflow else {}) or {}
    parties = []
    if best.get("complainant_name"):
        parties.append({"role": "complainant", "name": best["complainant_name"].value,
                        "address": best["complainant_address"].value if "complainant_address" in best else None,
                        "provenance": best["complainant_name"].provenance})
    if best.get("seller_name"):
        parties.append({"role": "opposite_party", "name": best["seller_name"].value,
                        "address": best["seller_address"].value if "seller_address" in best else None,
                        "provenance": best["seller_name"].provenance})
    timeline_events = []
    for key, label in (("purchase_date", "Purchase / payment"), ("problem_date", "Problem arose")):
        if key in best:
            timeline_events.append({"date": best[key].value, "label": label, "provenance": best[key].provenance})
    return {
        "case": ser.case_summary(case),
        "summary": case.incident_summary,
        "facts": [ser.fact(f) for f in facts],
        "fact_keys": [{"key": s.key, "label_en": s.label_en, "label_hi": s.label_hi, "value_type": s.value_type,
                       "required": s.required_for_draft} for s in SLOTS],
        "parties": parties,
        "incident_timeline": sorted(timeline_events, key=lambda e: e["date"]),
        "missing_information": missing_required(slots),
        "analysis": case.analysis or {},
        "workflow": {"status": workflow.status if workflow else None, "phase": state.get("phase"),
                     "category": state.get("category"), "category_confidence": state.get("category_confidence"),
                     "routing": state.get("routing"), "last_error": workflow.last_error if workflow else None,
                     "steps": [ser.step(s) for s in steps]},
        "deadlines": [ser.deadline(d, case.reference) for d in deadlines],
        "counts": counts,
    }


@router.patch("/cases/{case_id}")
async def rename_case(case_id: uuid.UUID, payload: CaseUpdateIn, ctx: RequestContext = Depends(get_context),
                      db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    case = await get_owned_case(db, case_id, ctx.user)
    case.title = payload.title.strip()
    return ser.case_summary(case)


@router.post("/cases/{case_id}/archive")
async def archive_case(case_id: uuid.UUID, archived: bool = True, ctx: RequestContext = Depends(get_context),
                       db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    case = await get_owned_case(db, case_id, ctx.user)
    case.archived_at = utcnow() if archived else None
    await record_audit(db, action="case.archive" if archived else "case.unarchive", actor_user_id=ctx.user.id,
                       resource_type="case", resource_id=case.id, case_id=case.id, ip_hash=ctx.ip_hash)
    return ser.case_summary(case)


@router.get("/cases/{case_id}/messages")
async def list_messages(case_id: uuid.UUID, ctx: RequestContext = Depends(get_context),
                        db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    case = await get_owned_case(db, case_id, ctx.user)
    conv = await db.scalar(select(Conversation).where(Conversation.case_id == case.id))
    if conv is None:
        return {"messages": [], "store_transcript": None}
    msgs = (await db.scalars(select(ConversationMessage).where(ConversationMessage.conversation_id == conv.id)
                             .order_by(ConversationMessage.created_at))).all()
    workflow = await db.scalar(select(WorkflowInstance).where(WorkflowInstance.case_id == case.id))
    return {"messages": [ser.message(m) for m in msgs], "store_transcript": conv.store_transcript,
            "asked_slot": ((workflow.state or {}).get("asked_slot") if workflow else None)}


@router.post("/cases/{case_id}/messages")
async def send_message(case_id: uuid.UUID, payload: MessageIn, ctx: RequestContext = Depends(get_context),
                       db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    case = await get_owned_case(db, case_id, ctx.user)
    if case.archived_at is not None:
        raise AppError("This case is archived. Restore it to continue.", code="case_archived")
    return await post_message(db, case, ctx, payload.text, payload.modality, payload.language)


@router.post("/cases/{case_id}/facts")
async def set_fact(case_id: uuid.UUID, payload: FactIn, ctx: RequestContext = Depends(get_context),
                   db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """The user enters or corrects a fact directly. Stored as user-confirmed."""
    case = await get_owned_case(db, case_id, ctx.user)
    if payload.key not in SLOT_BY_KEY:
        raise AppError("Unknown fact.", code="unknown_fact")
    value = payload.value.strip()
    vt = SLOT_BY_KEY[payload.key].value_type
    if vt == "date":
        try:
            value = date.fromisoformat(value[:10]).isoformat()
        except ValueError as exc:
            raise AppError("Enter the date as YYYY-MM-DD.", code="invalid_date") from exc
    elif vt == "money" and fact_service.parse_money(value) is None:
        raise AppError("Enter the amount as a number.", code="invalid_amount")
    # A direct user edit supersedes previous user values and any inference for this key.
    for f in await fact_service.active_facts(db, case.id):
        if f.key == payload.key and f.provenance == FactProvenance.AI_INFERENCE:
            f.status = FactStatus.REJECTED
    fact = await fact_service.upsert_fact(db, case.id, payload.key, value, FactProvenance.USER_CONFIRMED,
                                          value_type=vt, source_type="manual_edit")
    await fact_service.sync_case_columns(db, case)
    await record_audit(db, action="fact.set", actor_user_id=ctx.user.id, resource_type="case_fact",
                       resource_id=fact.id if fact else None, case_id=case.id, ip_hash=ctx.ip_hash,
                       meta={"key": payload.key})
    return ser.fact(fact) if fact else {}


async def _owned_fact(db: AsyncSession, case: Case, fact_id: uuid.UUID) -> CaseFact:
    fact = await db.scalar(select(CaseFact).where(CaseFact.id == fact_id, CaseFact.case_id == case.id))
    if fact is None:
        raise NotFoundError("Fact not found.")
    return fact


@router.post("/cases/{case_id}/facts/{fact_id}/confirm")
async def confirm_fact(case_id: uuid.UUID, fact_id: uuid.UUID, ctx: RequestContext = Depends(get_context),
                       db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    case = await get_owned_case(db, case_id, ctx.user)
    fact = await _owned_fact(db, case, fact_id)
    if fact.status != FactStatus.ACTIVE:
        raise AppError("This fact is no longer active.", code="fact_inactive")
    for other in await fact_service.active_facts(db, case.id):
        if other.key == fact.key and other.id != fact.id:
            other.status = FactStatus.SUPERSEDED
    fact.provenance = FactProvenance.USER_CONFIRMED
    fact.confirmed_at = utcnow()
    await fact_service.sync_case_columns(db, case)
    await record_audit(db, action="fact.confirm", actor_user_id=ctx.user.id, resource_type="case_fact",
                       resource_id=fact.id, case_id=case.id, ip_hash=ctx.ip_hash, meta={"key": fact.key})
    return ser.fact(fact)


@router.post("/cases/{case_id}/facts/{fact_id}/reject")
async def reject_fact(case_id: uuid.UUID, fact_id: uuid.UUID, ctx: RequestContext = Depends(get_context),
                      db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    case = await get_owned_case(db, case_id, ctx.user)
    fact = await _owned_fact(db, case, fact_id)
    fact.status = FactStatus.REJECTED
    await fact_service.sync_case_columns(db, case)
    await record_audit(db, action="fact.reject", actor_user_id=ctx.user.id, resource_type="case_fact",
                       resource_id=fact.id, case_id=case.id, ip_hash=ctx.ip_hash, meta={"key": fact.key})
    return ser.fact(fact)


@router.post("/cases/{case_id}/analysis/refresh")
async def refresh_analysis(case_id: uuid.UUID, ctx: RequestContext = Depends(get_context),
                           db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    case = await get_owned_case(db, case_id, ctx.user)
    result = await run_case_workflow(db, case, ctx.user, "refresh_analysis")
    return {"reply": result.reply, "cards": result.cards, "phase": result.phase, "case": ser.case_summary(case)}


@router.get("/cases/{case_id}/research")
async def case_research(case_id: uuid.UUID, ctx: RequestContext = Depends(get_context),
                        db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    case = await get_owned_case(db, case_id, ctx.user)
    rows = (await db.scalars(select(LegalCitation).where(LegalCitation.case_id == case.id)
                             .order_by(LegalCitation.created_at))).all()
    citations = []
    for c in rows:
        doc = c.chunk.document
        citations.append({
            "id": str(c.id), "topic": c.topic, "score": round(c.score, 4), "explanation": c.explanation,
            "explanation_language": c.explanation_language, "explanation_generated_by": c.explanation_generated_by,
            "section_ref": c.chunk.section_ref, "chapter": c.chunk.chapter, "text": c.chunk.text,
            "document": {"key": doc.key, "title": doc.title, "identifier": doc.identifier, "source_url": doc.source_url,
                         "source_name": doc.source.name if doc.source else None, "jurisdiction": doc.jurisdiction,
                         "publication_date": ser.iso(doc.publication_date), "effective_date": ser.iso(doc.effective_date),
                         "effective_date_note": doc.effective_date_note, "version_label": doc.version_label,
                         "verification_status": doc.verification_status, "verification_note": doc.verification_note,
                         "retrieved_at": ser.iso(doc.retrieved_at), "amends": doc.amends},
        })
    return {"citations": citations, "rule_outcomes": (case.analysis or {}).get("rule_outcomes", {}),
            "potential_routes": (case.analysis or {}).get("potential_routes", []),
            "limitations": [
                "Translations and explanations are aids to understanding; the English text from the official "
                "source is authoritative.",
                "The knowledge base holds the documents listed here. Later amendments not listed may exist.",
                "This is general legal information, not advice on your specific case from a lawyer.",
            ]}


@router.post("/cases/{case_id}/workflow/steps/{step_key}")
async def update_step(case_id: uuid.UUID, step_key: str, status: Literal["done", "pending"] = "done",
                      ctx: RequestContext = Depends(get_context), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    case = await get_owned_case(db, case_id, ctx.user)
    workflow = await db.scalar(select(WorkflowInstance).where(WorkflowInstance.case_id == case.id))
    step = await db.scalar(select(WorkflowStep).where(WorkflowStep.workflow_id == (workflow.id if workflow else None),
                                                      WorkflowStep.step_key == step_key))
    if step is None:
        raise NotFoundError("Step not found.")
    if step.owner != "user":
        raise AppError("This step is completed by NyayaSetu automatically.", code="system_step")
    step.status = StepStatus.DONE if status == "done" else StepStatus.PENDING
    return ser.step(step)


@router.get("/cases/{case_id}/agent-trace")
async def agent_trace(case_id: uuid.UUID, limit: int = Query(default=40, ge=1, le=200),
                      ctx: RequestContext = Depends(get_context), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Recorded agent runs for this case, plus the provisions behind each rule outcome, read from the
    knowledge base at request time (so the trace shows where every legal conclusion comes from)."""
    case = await get_owned_case(db, case_id, ctx.user)
    rows = (await db.scalars(select(AgentExecution).where(AgentExecution.case_id == case.id)
                             .order_by(AgentExecution.created_at.desc()).limit(limit))).all()
    executions = [{
        "stage": STAGES.get(r.agent, r.agent), "agent": r.agent, "status": r.status, "provider": r.provider,
        "model": r.model, "attempt": r.attempt, "latency_ms": r.latency_ms, "summary": r.summary or {},
        # Only the exception type: messages can echo user input.
        "error": (r.error or "").split(":", 1)[0] or None, "created_at": r.created_at.isoformat(),
    } for r in rows]
    outcomes: dict[str, Any] = (case.analysis or {}).get("rule_outcomes") or {}
    chunk_ids = {uuid.UUID(b["chunk_id"]) for o in outcomes.values() for b in o.get("basis", []) if b.get("chunk_id")}
    chunks = {c.id: c for c in (await db.scalars(select(LegalChunk).where(LegalChunk.id.in_(chunk_ids)))).all()}         if chunk_ids else {}
    provenance = []
    for key, outcome in outcomes.items():
        for b in outcome.get("basis", []):
            chunk = chunks.get(uuid.UUID(b["chunk_id"])) if b.get("chunk_id") else None
            provenance.append({
                "rule": key, "grounded": bool(outcome.get("grounded")), "section_ref": b.get("section_ref"),
                "summary": b.get("summary"), "document_title": chunk.document.title if chunk else b.get("document_title"),
                "source_url": chunk.document.source_url if chunk else b.get("source_url"),
                "chunk_id": b.get("chunk_id"), "in_knowledge_base": chunk is not None,
                "excerpt": " ".join(chunk.text.split())[:360] if chunk else None,
            })
    return {"executions": executions, "provenance": provenance, "fetched_at": utcnow().isoformat()}


@router.get("/cases/{case_id}/deadlines")
async def list_deadlines(case_id: uuid.UUID, ctx: RequestContext = Depends(get_context),
                         db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
    case = await get_owned_case(db, case_id, ctx.user)
    return [ser.deadline(d, case.reference) for d in (await db.scalars(
        select(Deadline).where(Deadline.case_id == case.id).order_by(Deadline.due_date))).all()]


@router.get("/cases/{case_id}/deadlines.ics")
async def deadlines_calendar(case_id: uuid.UUID, ctx: RequestContext = Depends(get_context),
                             db: AsyncSession = Depends(get_db)) -> Response:
    """Open deadlines as an iCalendar file for any calendar app."""
    case = await get_owned_case(db, case_id, ctx.user)
    rows = (await db.scalars(select(Deadline).where(Deadline.case_id == case.id,
                                                    Deadline.status == DeadlineStatus.OPEN)
                             .order_by(Deadline.due_date))).all()
    body = build_ics(rows, case.reference, utcnow())
    return Response(body, media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="nyayasetu-{case.reference}.ics"'})


@router.post("/cases/{case_id}/deadlines", status_code=201)
async def add_deadline(case_id: uuid.UUID, payload: DeadlineIn, ctx: RequestContext = Depends(get_context),
                       db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    case = await get_owned_case(db, case_id, ctx.user)
    basis = ("The reply deadline you set in your own legal notice. Not a period fixed by law."
             if payload.kind == DeadlineKind.LEGAL_NOTICE else "Added by you")
    d = Deadline(case_id=case.id, title=payload.title, due_date=payload.due_date, kind=DeadlineKind(payload.kind),
                 source=UpdateSource.USER_REPORTED, basis=basis, is_estimate=False,
                 reminder_days_before=payload.reminder_days_before)
    db.add(d)
    await db.flush()
    return ser.deadline(d, case.reference)


@router.patch("/cases/{case_id}/deadlines/{deadline_id}")
async def patch_deadline(case_id: uuid.UUID, deadline_id: uuid.UUID, payload: DeadlinePatch,
                         ctx: RequestContext = Depends(get_context), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    case = await get_owned_case(db, case_id, ctx.user)
    d = await db.scalar(select(Deadline).where(Deadline.id == deadline_id, Deadline.case_id == case.id))
    if d is None:
        raise NotFoundError("Deadline not found.")
    d.status = DeadlineStatus(payload.status)
    return ser.deadline(d, case.reference)


@router.get("/cases/{case_id}/updates")
async def list_updates(case_id: uuid.UUID, ctx: RequestContext = Depends(get_context),
                       db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
    case = await get_owned_case(db, case_id, ctx.user)
    rows = (await db.scalars(select(CaseUpdate).where(CaseUpdate.case_id == case.id)
                             .order_by(CaseUpdate.created_at.desc()))).all()
    return [ser.case_update(u) for u in rows]


@router.post("/cases/{case_id}/updates", status_code=201)
async def add_update(case_id: uuid.UUID, payload: UpdateIn, ctx: RequestContext = Depends(get_context),
                     db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """A user-reported update (e.g. a hearing date from a notice). Never shown as official status."""
    case = await get_owned_case(db, case_id, ctx.user)
    u = CaseUpdate(case_id=case.id, source=UpdateSource.USER_REPORTED, update_type=payload.update_type,
                   title=payload.title, body=payload.body, event_date=payload.event_date, verified=False,
                   created_by_user_id=ctx.user.id)
    db.add(u)
    if payload.update_type == "hearing" and payload.event_date:
        db.add(Deadline(case_id=case.id, title=f"Hearing: {payload.title}", due_date=payload.event_date,
                        kind=DeadlineKind.HEARING, source=UpdateSource.USER_REPORTED, is_estimate=False,
                        basis="Reported by you", reminder_days_before=3))
    await db.flush()
    await record_audit(db, action="case.update_reported", actor_user_id=ctx.user.id, resource_type="case_update",
                       resource_id=u.id, case_id=case.id, ip_hash=ctx.ip_hash, meta={"type": payload.update_type})
    return ser.case_update(u)


@router.get("/cases/{case_id}/activity")
async def activity(case_id: uuid.UUID, limit: int = Query(default=100, le=300), ctx: RequestContext = Depends(get_context),
                   db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
    case = await get_owned_case(db, case_id, ctx.user)
    rows = (await db.scalars(select(AuditLog).where(AuditLog.case_id == case.id)
                             .order_by(AuditLog.created_at.desc()).limit(limit))).all()
    return [{"id": str(r.id), "action": r.action, "actor_type": r.actor_type, "outcome": r.outcome,
             "resource_type": r.resource_type, "meta": r.meta, "created_at": ser.iso(r.created_at)} for r in rows]


@router.get("/cases/{case_id}/approvals")
async def list_approvals(case_id: uuid.UUID, ctx: RequestContext = Depends(get_context),
                         db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
    case = await get_owned_case(db, case_id, ctx.user)
    rows = (await db.scalars(select(Approval).where(Approval.case_id == case.id)
                             .order_by(Approval.created_at.desc()))).all()
    return [ser.approval(a) for a in rows]
