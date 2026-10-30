"""SQLAlchemy models. Importing this package registers every table on Base.metadata."""

from app.models.case import Case, CaseFact, CaseParty, CaseUpdate, Deadline
from app.models.conversation import Conversation, ConversationMessage, VoiceSession
from app.models.document import (
    DocumentExtraction,
    DocumentVersion,
    EvidenceItem,
    GeneratedDocument,
    UploadedDocument,
)
from app.models.legal import LegalChunk, LegalCitation, LegalDocument, LegalSource
from app.models.system import AuditLog, IntegrationConfig, Notification
from app.models.user import AuthSession, PasswordResetToken, User, UserPreferences
from app.models.workflow import (
    AgentExecution,
    Approval,
    BackgroundJob,
    FilingRecord,
    WorkflowInstance,
    WorkflowStep,
)

__all__ = [
    "AgentExecution",
    "Approval",
    "AuditLog",
    "AuthSession",
    "BackgroundJob",
    "Case",
    "CaseFact",
    "CaseParty",
    "CaseUpdate",
    "Conversation",
    "ConversationMessage",
    "Deadline",
    "DocumentExtraction",
    "DocumentVersion",
    "EvidenceItem",
    "FilingRecord",
    "GeneratedDocument",
    "IntegrationConfig",
    "LegalChunk",
    "LegalCitation",
    "LegalDocument",
    "LegalSource",
    "Notification",
    "PasswordResetToken",
    "UploadedDocument",
    "User",
    "UserPreferences",
    "VoiceSession",
    "WorkflowInstance",
    "WorkflowStep",
]
