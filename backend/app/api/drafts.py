"""Generated documents, approval gates and filing.

Approval rules (docs/LEGAL_SAFETY.md):
  * A document approval is bound to one version's content hash. Editing creates a new
    version, which is a draft again and needs a fresh approval.
  * Filing requires (a) every core document approved at its current version and (b) an
    explicit SUBMIT_FILING authorisation over exactly those versions, which expires.
  * NyayaSetu never submits to the portal. A filing is recorded as "submitted (user reported)"
    only when the user enters the acknowledgement they received.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import date, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.graph import CORE_DOCUMENTS, run_case_workflow
from app.agents.planning import sync_admissibility_deadline
from app.api import serializers as ser
from app.core.audit import record_audit
from app.core.deps import RequestContext, get_context, get_owned_case
from app.core.errors import AppError, ApprovalRequiredError, ConflictError, IntegrationUnavailableError, NotFoundError
from app.db.base import utcnow
from app.db.session import get_db
from app.documents.render import render_docx, render_pdf
from app.integrations import browser_assist, ejagriti
from app.integrations import ejagriti_copilot as copilot
from app.models import Approval, Case, CaseUpdate, DocumentVersion, FilingRecord, GeneratedDocument, UploadedDocument
from app.models.enums import (
    ApprovalAction,
    ApprovalStatus,
    CaseStatus,
    FilingMode,
    FilingStatus,
    GeneratedDocStatus,
    UpdateSource,
)
from app.services.documents import current_version, edit_document, get_document
from app.services.facts import load_slots

router = APIRouter(tags=["drafts", "filing"])

APPROVAL_STATEMENT = (
    "I have read this document. The facts in it are true to my knowledge, and I approve this exact version. "
    "I understand NyayaSetu is not a lawyer and does not file or sign on my behalf."
)
FILING_STATEMENT = (
    "I authorise NyayaSetu to prepare my approved documents and details for filing on the official e-Jagriti "
    "portal. I will log in, review and submit on the portal myself."
)
SHARE_STATEMENT = (
    "I allow NyayaSetu's browser assistant to enter my approved details into the official portal in a browser "
    "window that I can see. It will not submit, pay or sign."
)


class EditIn(BaseModel):
    edits: dict[str, str] = Field(min_length=1, max_length=40)
    note: str | None = Field(default=None, max_length=500)


class ApproveIn(BaseModel):
    version_number: int
    content_sha256: str = Field(min_length=64, max_length=64)
    statement_accepted: bool
    acknowledge_warnings: bool = False


class AuthorizeIn(BaseModel):
    statement_accepted: bool
    allow_browser_assist: bool = False


class StartIn(BaseModel):
    mode: Literal["guided", "browser_assist"] = "guided"


class ChecklistIn(BaseModel):
    key: str = Field(max_length=40)
    done: bool


class AcknowledgementIn(BaseModel):
    acknowledgement_number: str = Field(min_length=3, max_length=120, pattern=r"^[A-Za-z0-9/\-_. ]+$")
    submitted_on: date
    document_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=1000)


def _outcomes(case: Case) -> dict[str, Any]:
    return (case.analysis or {}).get("rule_outcomes", {})


async def _core_docs(db: AsyncSession, case_id: uuid.UUID) -> list[GeneratedDocument]:
    return list((await db.scalars(select(GeneratedDocument).where(
        GeneratedDocument.case_id == case_id, GeneratedDocument.doc_type.in_(CORE_DOCUMENTS))
        .options(selectinload(GeneratedDocument.versions)))).all())


async def _approved_versions(db: AsyncSession, case: Case) -> tuple[list[str], list[str]]:
    """Return (approved current version ids, blockers)."""
    docs = await _core_docs(db, case.id)
    by_type = {d.doc_type: d for d in docs}
    blockers, version_ids = [], []
    for doc_type in CORE_DOCUMENTS:
        doc = by_type.get(doc_type)
        if doc is None:
            blockers.append(f"{doc_type} has not been generated")
            continue
        v = current_version(doc)
        approval = await db.scalar(select(Approval).where(
            Approval.case_id == case.id, Approval.action == ApprovalAction.APPROVE_DOCUMENT,
            Approval.target_id == doc.id, Approval.status == ApprovalStatus.APPROVED,
            Approval.content_sha256 == v.content_sha256))
        if doc.status != GeneratedDocStatus.APPROVED or approval is None:
            blockers.append(f"{doc.title} is not approved at its current version")
        else:
            version_ids.append(str(v.id))
    return version_ids, blockers


def _bundle_hash(version_ids: list[str]) -> str:
    return hashlib.sha256("|".join(sorted(version_ids)).encode()).hexdigest()


async def valid_authorization(db: AsyncSession, case: Case, action: ApprovalAction) -> Approval | None:
    version_ids, blockers = await _approved_versions(db, case)
    if blockers:
        return None
    approval = await db.scalar(select(Approval).where(
        Approval.case_id == case.id, Approval.action == action, Approval.status == ApprovalStatus.APPROVED,
        Approval.content_sha256 == _bundle_hash(version_ids)).order_by(Approval.created_at.desc()))
    if approval is None:
        return None
    expires = approval.expires_at
    if expires is not None:
        from datetime import UTC

        if (expires if expires.tzinfo else expires.replace(tzinfo=UTC)) < utcnow():
            approval.status = ApprovalStatus.EXPIRED
            return None
    return approval


# ---- drafts -----------------------------------------------------------------------------------------


@router.post("/cases/{case_id}/drafts/generate")
async def generate(case_id: uuid.UUID, ctx: RequestContext = Depends(get_context),
                   db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    case = await get_owned_case(db, case_id, ctx.user)
    result = await run_case_workflow(db, case, ctx.user, "generate_documents")
    await record_audit(db, action="drafts.generate", actor_user_id=ctx.user.id, case_id=case.id, ip_hash=ctx.ip_hash)
    return {"reply": result.reply, "cards": result.cards, "phase": result.phase, "case": ser.case_summary(case)}


@router.get("/cases/{case_id}/drafts")
async def list_drafts(case_id: uuid.UUID, ctx: RequestContext = Depends(get_context),
                      db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
    case = await get_owned_case(db, case_id, ctx.user)
    docs = (await db.scalars(select(GeneratedDocument).where(GeneratedDocument.case_id == case.id)
                             .options(selectinload(GeneratedDocument.versions))
                             .order_by(GeneratedDocument.created_at))).all()
    return [ser.generated(d) for d in docs]


@router.get("/cases/{case_id}/drafts/{doc_id}")
async def get_draft(case_id: uuid.UUID, doc_id: uuid.UUID, ctx: RequestContext = Depends(get_context),
                    db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    case = await get_owned_case(db, case_id, ctx.user)
    doc = await get_document(db, case.id, doc_id)
    approvals = (await db.scalars(select(Approval).where(Approval.target_id == doc.id)
                                  .order_by(Approval.created_at.desc()))).all()
    return {**ser.generated(doc, include_versions=True), "approvals": [ser.approval(a) for a in approvals],
            "approval_statement": APPROVAL_STATEMENT}


@router.put("/cases/{case_id}/drafts/{doc_id}")
async def edit_draft(case_id: uuid.UUID, doc_id: uuid.UUID, payload: EditIn, ctx: RequestContext = Depends(get_context),
                     db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    case = await get_owned_case(db, case_id, ctx.user)
    version = await edit_document(db, case.id, doc_id, payload.edits, payload.note, _outcomes(case), date.today())
    await record_audit(db, action="draft.edit", actor_user_id=ctx.user.id, resource_type="generated_document",
                       resource_id=doc_id, case_id=case.id, ip_hash=ctx.ip_hash,
                       meta={"version": version.version_number, "blocks": list(payload.edits)})
    doc = await get_document(db, case.id, doc_id)
    return ser.generated(doc, include_versions=True)


@router.get("/cases/{case_id}/drafts/{doc_id}/download")
async def download_draft(case_id: uuid.UUID, doc_id: uuid.UUID, format: Literal["pdf", "docx"] = "pdf",
                         version: int | None = Query(default=None, ge=1), ctx: RequestContext = Depends(get_context),
                         db: AsyncSession = Depends(get_db)) -> Response:
    case = await get_owned_case(db, case_id, ctx.user)
    doc = await get_document(db, case.id, doc_id)
    target = next((v for v in doc.versions if v.version_number == (version or doc.current_version)), None)
    if target is None:
        raise NotFoundError("Version not found.")
    approved = doc.status == GeneratedDocStatus.APPROVED and target.version_number == doc.current_version
    label = f"v{target.version_number}" + (" (approved)" if approved else "")
    if format == "pdf":
        data, media = render_pdf(target.content, version_label=label, draft=not approved), "application/pdf"
    else:
        data = render_docx(target.content, version_label=label, draft=not approved)
        media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    name = f"{doc.doc_type}_{case.reference}_v{target.version_number}.{format}"
    await record_audit(db, action="draft.download", actor_user_id=ctx.user.id, resource_type="generated_document",
                       resource_id=doc.id, case_id=case.id, ip_hash=ctx.ip_hash, meta={"format": format})
    return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"',
                                                     "Cache-Control": "no-store"})


@router.post("/cases/{case_id}/drafts/{doc_id}/approve")
async def approve_draft(case_id: uuid.UUID, doc_id: uuid.UUID, payload: ApproveIn,
                        ctx: RequestContext = Depends(get_context), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    case = await get_owned_case(db, case_id, ctx.user)
    doc = await get_document(db, case.id, doc_id)
    v = current_version(doc)
    if not payload.statement_accepted:
        raise ApprovalRequiredError("Please read and accept the approval statement.")
    if payload.version_number != v.version_number or payload.content_sha256 != v.content_sha256:
        raise ConflictError("This document changed since you opened it. Please review the latest version.",
                            code="version_mismatch")
    validation = v.validation or {}
    if validation.get("status") == "blocked":
        raise AppError("This document has problems that must be fixed before approval.", code="validation_blocked",
                       details=[i for i in validation.get("issues", []) if i["severity"] == "blocker"])
    if validation.get("status") == "needs_attention" and not payload.acknowledge_warnings:
        raise ApprovalRequiredError("Please confirm you have read the warnings for this document.",
                                    details=validation.get("issues", []))
    approval = Approval(case_id=case.id, user_id=ctx.user.id, action=ApprovalAction.APPROVE_DOCUMENT,
                        status=ApprovalStatus.APPROVED, target_type="generated_document", target_id=doc.id,
                        document_version_ids=[str(v.id)], content_sha256=v.content_sha256,
                        statement=APPROVAL_STATEMENT, decided_at=utcnow(), ip_hash=ctx.ip_hash,
                        user_agent=ctx.user_agent)
    db.add(approval)
    doc.status = GeneratedDocStatus.APPROVED
    await db.flush()
    await record_audit(db, action="draft.approve", actor_user_id=ctx.user.id, resource_type="generated_document",
                       resource_id=doc.id, case_id=case.id, ip_hash=ctx.ip_hash,
                       meta={"version": v.version_number, "sha256": v.content_sha256[:16]})
    result = await run_case_workflow(db, case, ctx.user, "approval_decided")
    return {"document": ser.generated(doc), "approval": ser.approval(approval), "reply": result.reply,
            "phase": result.phase}


@router.post("/cases/{case_id}/drafts/{doc_id}/revoke-approval")
async def revoke_approval(case_id: uuid.UUID, doc_id: uuid.UUID, ctx: RequestContext = Depends(get_context),
                          db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    case = await get_owned_case(db, case_id, ctx.user)
    doc = await get_document(db, case.id, doc_id)
    for a in (await db.scalars(select(Approval).where(Approval.target_id == doc.id,
                                                      Approval.status == ApprovalStatus.APPROVED))).all():
        a.status = ApprovalStatus.REVOKED
    doc.status = GeneratedDocStatus.DRAFT
    await record_audit(db, action="draft.approval_revoked", actor_user_id=ctx.user.id,
                       resource_type="generated_document", resource_id=doc.id, case_id=case.id, ip_hash=ctx.ip_hash)
    return ser.generated(doc)


# ---- filing -----------------------------------------------------------------------------------------


@router.get("/cases/{case_id}/filing")
async def filing_overview(case_id: uuid.UUID, ctx: RequestContext = Depends(get_context),
                          db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    case = await get_owned_case(db, case_id, ctx.user)
    version_ids, blockers = await _approved_versions(db, case)
    authorization = await valid_authorization(db, case, ApprovalAction.SUBMIT_FILING)
    record = await db.scalar(select(FilingRecord).where(FilingRecord.case_id == case.id)
                             .order_by(FilingRecord.created_at.desc()))
    outcomes = _outcomes(case)
    forum = (outcomes.get("pecuniary_forum") or {}).get("value")
    lang = case.language
    context = {
        "forum_label": {"district": "the District Commission", "state": "the State Commission",
                        "national": "the National Commission"}.get(forum or ""),
        "fee_text": (outcomes.get("filing_fee") or {}).get("explanation_hi" if lang == "hi" else "explanation_en"),
    }
    return {
        "portal": ejagriti.PORTAL_NAME, "portal_url": ejagriti.get_settings().ejagriti_base_url,
        "capabilities": ejagriti.capabilities().as_dict(), "upload_rules": ejagriti.UPLOAD_RULES,
        "ready": not blockers, "blockers": blockers, "approved_version_ids": version_ids,
        "authorized": authorization is not None,
        "authorization": ser.approval(authorization) if authorization else None,
        "authorization_statement": FILING_STATEMENT, "share_statement": SHARE_STATEMENT,
        "guided_steps": ejagriti.guided_steps(context, lang),
        "data_sheet": ejagriti.data_sheet(dict(await load_slots(db, case.id))),
        "record": ser.filing(record) if record else None,
    }


@router.post("/cases/{case_id}/filing/authorize")
async def authorize_filing(case_id: uuid.UUID, payload: AuthorizeIn, ctx: RequestContext = Depends(get_context),
                           db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    case = await get_owned_case(db, case_id, ctx.user)
    if not payload.statement_accepted:
        raise ApprovalRequiredError("Please read and accept the authorisation statement.")
    version_ids, blockers = await _approved_versions(db, case)
    if blockers:
        raise AppError("All documents must be approved before filing.", code="documents_not_approved", details=blockers)
    created = []
    actions = [(ApprovalAction.SUBMIT_FILING, FILING_STATEMENT)]
    if payload.allow_browser_assist:
        actions.append((ApprovalAction.SHARE_EXTERNAL, SHARE_STATEMENT))
    for action, statement in actions:
        approval = Approval(case_id=case.id, user_id=ctx.user.id, action=action, status=ApprovalStatus.APPROVED,
                            target_type="case", target_id=case.id, document_version_ids=version_ids,
                            content_sha256=_bundle_hash(version_ids), statement=statement, decided_at=utcnow(),
                            expires_at=utcnow() + timedelta(days=7), ip_hash=ctx.ip_hash, user_agent=ctx.user_agent)
        db.add(approval)
        created.append(approval)
    await db.flush()
    await record_audit(db, action="filing.authorize", actor_user_id=ctx.user.id, resource_type="case",
                       resource_id=case.id, case_id=case.id, ip_hash=ctx.ip_hash,
                       meta={"actions": [a.action for a in created]})
    return {"approvals": [ser.approval(a) for a in created]}


@router.post("/cases/{case_id}/filing/start")
async def start_filing(case_id: uuid.UUID, payload: StartIn, ctx: RequestContext = Depends(get_context),
                       db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    case = await get_owned_case(db, case_id, ctx.user)
    authorization = await valid_authorization(db, case, ApprovalAction.SUBMIT_FILING)
    if authorization is None:
        raise ApprovalRequiredError("Filing needs your authorisation over the current approved documents.")
    if payload.mode == "browser_assist":
        if not ejagriti.capabilities().browser_assist:
            raise IntegrationUnavailableError("Browser assistance is not available on this server. Use guided filing.")
        if await valid_authorization(db, case, ApprovalAction.SHARE_EXTERNAL) is None:
            raise ApprovalRequiredError("Browser assistance needs your permission to enter details on the portal.")
    record = FilingRecord(case_id=case.id, portal="e_jagriti", mode=FilingMode(payload.mode),
                          status=FilingStatus.IN_PROGRESS, approval_id=authorization.id,
                          document_version_ids=authorization.document_version_ids, checklist_state={})
    db.add(record)
    case.status = CaseStatus.READY_TO_FILE
    await db.flush()
    await record_audit(db, action="filing.start", actor_user_id=ctx.user.id, resource_type="filing_record",
                       resource_id=record.id, case_id=case.id, ip_hash=ctx.ip_hash, meta={"mode": payload.mode})
    return ser.filing(record)


async def _owned_filing(db: AsyncSession, case: Case, filing_id: uuid.UUID) -> FilingRecord:
    record = await db.scalar(select(FilingRecord).where(FilingRecord.id == filing_id, FilingRecord.case_id == case.id))
    if record is None:
        raise NotFoundError("Filing record not found.")
    return record


@router.post("/cases/{case_id}/filing/{filing_id}/checklist")
async def update_checklist(case_id: uuid.UUID, filing_id: uuid.UUID, payload: ChecklistIn,
                           ctx: RequestContext = Depends(get_context), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    case = await get_owned_case(db, case_id, ctx.user)
    record = await _owned_filing(db, case, filing_id)
    record.checklist_state = {**(record.checklist_state or {}), payload.key: payload.done}
    return ser.filing(record)


@router.post("/cases/{case_id}/filing/{filing_id}/browser-assist")
async def run_browser_assist(case_id: uuid.UUID, filing_id: uuid.UUID, ctx: RequestContext = Depends(get_context),
                             db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    case = await get_owned_case(db, case_id, ctx.user)
    record = await _owned_filing(db, case, filing_id)
    if record.mode != FilingMode.BROWSER_ASSIST:
        raise AppError("This filing uses guided mode.", code="wrong_mode")
    if await valid_authorization(db, case, ApprovalAction.SHARE_EXTERNAL) is None:
        raise ApprovalRequiredError("Browser assistance needs your permission to enter details on the portal.")
    try:
        report = await browser_assist.open_portal(ejagriti.get_settings().ejagriti_base_url)
    except browser_assist.BrowserAssistUnavailable as exc:
        raise IntegrationUnavailableError(str(exc)) from exc
    record.portal_state = {**report.as_dict(), "checked_at": ser.iso(utcnow())}
    await record_audit(db, action="filing.browser_assist", actor_user_id=ctx.user.id, resource_type="filing_record",
                       resource_id=record.id, case_id=case.id, ip_hash=ctx.ip_hash, meta={"state": report.state})
    return ser.filing(record)


@router.get("/cases/{case_id}/filing/{filing_id}/copilot-bundle")
async def copilot_bundle(case_id: uuid.UUID, filing_id: uuid.UUID, ctx: RequestContext = Depends(get_context),
                         db: AsyncSession = Depends(get_db)) -> Response:
    """ZIP with the approved PDFs, a packet of confirmed details and a local Playwright co-pilot script.

    Needs both filing authorisations over the current approved versions. The script runs on the
    citizen's computer and stops at HITL_AWAITING_CITIZEN_OTP_AND_SUBMIT; it never submits."""
    case = await get_owned_case(db, case_id, ctx.user)
    record = await _owned_filing(db, case, filing_id)
    if record.status == FilingStatus.VERIFIED:
        raise ConflictError("This filing has already been verified.", code="filing_verified")
    if await valid_authorization(db, case, ApprovalAction.SUBMIT_FILING) is None or             await valid_authorization(db, case, ApprovalAction.SHARE_EXTERNAL) is None:
        raise ApprovalRequiredError("The co-pilot needs your filing authorisation, including permission to "
                                    "enter your details on the portal, over the current approved documents.")
    version_ids, _ = await _approved_versions(db, case)
    versions = (await db.scalars(select(DocumentVersion).where(
        DocumentVersion.id.in_([uuid.UUID(v) for v in version_ids])))).all()
    docs = {d.id: d for d in await _core_docs(db, case.id)}
    packet_docs = []
    for v in sorted(versions, key=lambda v: CORE_DOCUMENTS.index(docs[v.generated_document_id].doc_type)):
        doc = docs[v.generated_document_id]
        packet_docs.append(copilot.PacketDocument(
            doc_type=doc.doc_type, title=doc.title, filename=f"{doc.doc_type}_{case.reference}_v{v.version_number}.pdf",
            pdf=render_pdf(v.content, version_label=f"v{v.version_number} (approved)", draft=False),
            version_number=v.version_number, content_sha256=v.content_sha256))
    forum = ((case.analysis or {}).get("rule_outcomes", {}).get("pecuniary_forum") or {})
    packet = copilot.build_packet(
        case_reference=case.reference, portal_url=ejagriti.get_settings().ejagriti_base_url,
        data_sheet=ejagriti.data_sheet(await load_slots(db, case.id)),
        forum=str(forum["value"]).capitalize() if forum.get("grounded") and forum.get("value") else None,
        documents=packet_docs, generated_at=utcnow())
    await record_audit(db, action="filing.copilot_bundle", actor_user_id=ctx.user.id, resource_type="filing_record",
                       resource_id=record.id, case_id=case.id, ip_hash=ctx.ip_hash,
                       meta={"documents": len(packet_docs)})
    return Response(copilot.build_bundle(packet, packet_docs), media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="nyayasetu-copilot-{case.reference}.zip"',
        "Cache-Control": "no-store"})


@router.post("/cases/{case_id}/filing/{filing_id}/acknowledgement")
async def record_acknowledgement(case_id: uuid.UUID, filing_id: uuid.UUID, payload: AcknowledgementIn,
                                 ctx: RequestContext = Depends(get_context),
                                 db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    case = await get_owned_case(db, case_id, ctx.user)
    record = await _owned_filing(db, case, filing_id)
    if record.status == FilingStatus.VERIFIED:
        raise ConflictError("This filing has been verified on the official portal and can no longer be changed.",
                            code="filing_verified")
    if payload.submitted_on > date.today():
        raise AppError("The submission date cannot be in the future.", code="invalid_date")
    if payload.document_id:
        upload = await db.scalar(select(UploadedDocument).where(UploadedDocument.id == payload.document_id,
                                                                UploadedDocument.case_id == case.id))
        if upload is None:
            raise NotFoundError("Acknowledgement document not found.")
    record.acknowledgement_number = payload.acknowledgement_number.strip()
    record.acknowledgement_source = UpdateSource.USER_REPORTED
    record.acknowledgement_document_id = payload.document_id
    record.submitted_at = utcnow()
    record.status = FilingStatus.SUBMITTED_USER_REPORTED
    record.notes = payload.notes
    if record.approval_id:
        approval = await db.get(Approval, record.approval_id)
        if approval and approval.status == ApprovalStatus.APPROVED:
            approval.status = ApprovalStatus.CONSUMED
            approval.consumed_at = utcnow()
    case.status = CaseStatus.FILED_USER_REPORTED
    db.add(CaseUpdate(case_id=case.id, source=UpdateSource.USER_REPORTED, update_type="filing",
                      title=f"Complaint submitted on e-Jagriti (reference {record.acknowledgement_number})",
                      body="Reported by you. Not yet verified against the official portal.",
                      event_date=payload.submitted_on, verified=False, created_by_user_id=ctx.user.id))
    await sync_admissibility_deadline(db, case.id, payload.submitted_on)
    await db.flush()
    await record_audit(db, action="filing.acknowledgement_recorded", actor_user_id=ctx.user.id,
                       resource_type="filing_record", resource_id=record.id, case_id=case.id, ip_hash=ctx.ip_hash,
                       meta={"source": "user_reported"})
    result = await run_case_workflow(db, case, ctx.user, "filing_update")
    return {"filing": ser.filing(record), "reply": result.reply, "case": ser.case_summary(case)}
