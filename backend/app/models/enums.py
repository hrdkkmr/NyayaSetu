"""Domain enumerations. Stored as strings for portability across databases."""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    CITIZEN = "citizen"
    LEGAL_REVIEWER = "legal_reviewer"
    ADMIN = "admin"


class Language(StrEnum):
    EN = "en"
    HI = "hi"


class CaseStatus(StrEnum):
    INTAKE = "intake"
    RESEARCH = "research"
    PLANNING = "planning"
    DRAFTING = "drafting"
    REVIEW = "review"
    AWAITING_APPROVAL = "awaiting_approval"
    READY_TO_FILE = "ready_to_file"
    FILED_USER_REPORTED = "filed_user_reported"
    FILED_VERIFIED = "filed_verified"
    NEEDS_PROFESSIONAL_REVIEW = "needs_professional_review"
    CLOSED = "closed"
    ARCHIVED = "archived"


class FactProvenance(StrEnum):
    """Where a fact came from. Inferences are never silently promoted to confirmed."""

    USER_CONFIRMED = "user_confirmed"
    USER_STATED = "user_stated"
    DOCUMENT_EXTRACTED = "document_extracted"
    AI_INFERENCE = "ai_inference"


class FactStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class PartyRole(StrEnum):
    COMPLAINANT = "complainant"
    OPPOSITE_PARTY = "opposite_party"
    WITNESS = "witness"
    OTHER = "other"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    NOTICE = "notice"


class Modality(StrEnum):
    TEXT = "text"
    VOICE = "voice"


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    NEEDS_OCR = "needs_ocr"
    FAILED = "failed"
    REJECTED = "rejected"


class GeneratedDocStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    SUPERSEDED = "superseded"


class VerificationStatus(StrEnum):
    FETCHED_OFFICIAL = "fetched_official"
    VERIFIED_BY_REVIEWER = "verified_by_reviewer"
    UNVERIFIED = "unverified"
    STALE = "stale"


class WorkflowStatus(StrEnum):
    RUNNING = "running"
    WAITING_USER = "waiting_user"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"


class StepStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class ApprovalAction(StrEnum):
    APPROVE_DOCUMENT = "approve_document"
    SUBMIT_FILING = "submit_filing"
    SIGN_DOCUMENT = "sign_document"
    SEND_LEGAL_NOTICE = "send_legal_notice"
    SHARE_EXTERNAL = "share_external"
    MAKE_PAYMENT = "make_payment"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVOKED = "revoked"
    CONSUMED = "consumed"
    EXPIRED = "expired"


class FilingMode(StrEnum):
    GUIDED = "guided"
    BROWSER_ASSIST = "browser_assist"


class FilingStatus(StrEnum):
    PREPARING = "preparing"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    SUBMITTED_USER_REPORTED = "submitted_user_reported"
    VERIFIED = "verified"
    FAILED = "failed"
    ABANDONED = "abandoned"


class UpdateSource(StrEnum):
    """Who asserted a case update. Only OFFICIAL_PORTAL may be shown as official status."""

    INTERNAL = "internal"
    USER_REPORTED = "user_reported"
    OFFICIAL_PORTAL = "official_portal"


class DeadlineKind(StrEnum):
    LIMITATION = "limitation"
    HEARING = "hearing"
    RESPONSE = "response"
    USER = "user"
    ADMISSIBILITY = "admissibility"  # statutory target, CPA 2019 s. 36(2)
    LEGAL_NOTICE = "legal_notice"    # the reply deadline the user set in their own notice (not statutory)


class DeadlineStatus(StrEnum):
    OPEN = "open"
    DONE = "done"
    MISSED = "missed"
    DISMISSED = "dismissed"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
