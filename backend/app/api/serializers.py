"""Explicit serializers. API responses never include storage keys, raw paths or secrets."""

from __future__ import annotations

from typing import Any

from app.models import (
    Approval,
    Case,
    CaseFact,
    CaseUpdate,
    ConversationMessage,
    Deadline,
    DocumentVersion,
    EvidenceItem,
    FilingRecord,
    GeneratedDocument,
    Notification,
    UploadedDocument,
    WorkflowStep,
)
from app.services.calendar import google_calendar_url


def iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def case_summary(case: Case) -> dict[str, Any]:
    return {
        "id": str(case.id), "reference": case.reference, "title": case.title, "category": case.category,
        "status": case.status, "language": case.language, "incident_date": iso(case.incident_date),
        "financial_amount": str(case.financial_amount) if case.financial_amount is not None else None,
        "location_district": case.location_district, "location_state": case.location_state,
        "requires_human_review": case.requires_human_review, "archived": case.archived_at is not None,
        "created_at": iso(case.created_at), "updated_at": iso(case.updated_at),
    }


def fact(f: CaseFact) -> dict[str, Any]:
    return {
        "id": str(f.id), "key": f.key, "value": f.value, "value_type": f.value_type, "provenance": f.provenance,
        "status": f.status, "source_type": f.source_type, "source_id": f.source_id, "excerpt": f.source_excerpt,
        "confidence": f.confidence, "confirmed_at": iso(f.confirmed_at), "created_at": iso(f.created_at),
    }


def message(m: ConversationMessage) -> dict[str, Any]:
    return {
        "id": str(m.id), "role": m.role, "content": m.content, "language": m.language, "modality": m.modality,
        "redacted": m.redacted, "cards": (m.meta or {}).get("cards", []), "created_at": iso(m.created_at),
    }


def step(s: WorkflowStep) -> dict[str, Any]:
    return {
        "key": s.step_key, "title": s.title, "title_hi": s.title_hi, "description": s.description,
        "status": s.status, "owner": s.owner, "order": s.order_index, "due_date": iso(s.due_date),
        "refs": s.source_refs or [],
    }


def deadline(d: Deadline, case_reference: str | None = None) -> dict[str, Any]:
    out = {
        "id": str(d.id), "title": d.title, "due_date": iso(d.due_date), "kind": d.kind, "status": d.status,
        "source": d.source, "basis": d.basis, "is_estimate": d.is_estimate,
        "citation_chunk_id": str(d.citation_chunk_id) if d.citation_chunk_id else None,
    }
    if case_reference:
        out["google_calendar_url"] = google_calendar_url(d, case_reference)
    return out


def case_update(u: CaseUpdate) -> dict[str, Any]:
    return {
        "id": str(u.id), "source": u.source, "update_type": u.update_type, "title": u.title, "body": u.body,
        "event_date": iso(u.event_date), "verified": u.verified, "source_reference": u.source_reference,
        "created_at": iso(u.created_at),
    }


def upload(d: UploadedDocument, include_text: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": str(d.id), "filename": d.original_filename, "content_type": d.content_type,
        "size_bytes": d.size_bytes, "status": d.status, "document_class": d.document_class,
        "page_count": d.page_count, "security_flags": d.security_flags or [], "error": d.error,
        "created_at": iso(d.created_at),
    }
    if d.extraction is not None:
        out["extraction"] = {
            "method": d.extraction.method, "language_hint": d.extraction.language_hint,
            "fields": d.extraction.fields or {}, "injection_flags": d.extraction.injection_flags or [],
            "reviewed_at": iso(d.extraction.reviewed_at),
            "text_preview": d.extraction.text[:4000] if include_text else None,
            "text_length": len(d.extraction.text or ""),
        }
    return out


def evidence(e: EvidenceItem) -> dict[str, Any]:
    return {
        "id": str(e.id), "label": e.label, "title": e.title, "description": e.description,
        "evidence_type": e.evidence_type, "evidence_date": iso(e.evidence_date), "order_index": e.order_index,
        "document_id": str(e.document_id) if e.document_id else None, "confirmed_by_user": e.confirmed_by_user,
    }


def version(v: DocumentVersion, include_content: bool = True) -> dict[str, Any]:
    out = {
        "id": str(v.id), "version_number": v.version_number, "content_sha256": v.content_sha256,
        "created_by": v.created_by, "change_note": v.change_note, "validation": v.validation or {},
        "source_trace": v.source_trace or {}, "created_at": iso(v.created_at),
    }
    if include_content:
        out["content"] = v.content
    return out


def generated(doc: GeneratedDocument, include_versions: bool = False) -> dict[str, Any]:
    current = next((v for v in doc.versions if v.version_number == doc.current_version), None)
    out: dict[str, Any] = {
        "id": str(doc.id), "doc_type": doc.doc_type, "title": doc.title, "status": doc.status,
        "language": doc.language, "template": f"{doc.template_id}@{doc.template_version}",
        "current_version": doc.current_version, "updated_at": iso(doc.updated_at),
        "validation_status": (current.validation or {}).get("status") if current else None,
    }
    if include_versions:
        out["versions"] = [version(v, include_content=v.version_number == doc.current_version) for v in doc.versions]
    return out


def approval(a: Approval) -> dict[str, Any]:
    return {
        "id": str(a.id), "action": a.action, "status": a.status, "target_type": a.target_type,
        "target_id": str(a.target_id), "document_version_ids": a.document_version_ids or [],
        "content_sha256": a.content_sha256, "statement": a.statement, "decided_at": iso(a.decided_at),
        "expires_at": iso(a.expires_at), "consumed_at": iso(a.consumed_at), "created_at": iso(a.created_at),
    }


def filing(f: FilingRecord) -> dict[str, Any]:
    return {
        "id": str(f.id), "portal": f.portal, "mode": f.mode, "status": f.status,
        "approval_id": str(f.approval_id) if f.approval_id else None,
        "acknowledgement_number": f.acknowledgement_number, "acknowledgement_source": f.acknowledgement_source,
        "acknowledgement_document_id": str(f.acknowledgement_document_id) if f.acknowledgement_document_id else None,
        "submitted_at": iso(f.submitted_at), "verified_at": iso(f.verified_at),
        "checklist_state": f.checklist_state or {}, "portal_state": f.portal_state or {}, "notes": f.notes,
        "created_at": iso(f.created_at),
    }


def notification(n: Notification) -> dict[str, Any]:
    return {
        "id": str(n.id), "kind": n.kind, "title": n.title, "body": n.body, "link": n.link,
        "case_id": str(n.case_id) if n.case_id else None, "read": n.read_at is not None,
        "created_at": iso(n.created_at),
    }
