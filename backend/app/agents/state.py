"""Workflow state for the case graph.

The database is the source of truth for facts (`case_facts`). `slots` in the state
is rebuilt from the database at the start of every run, so a fact the user edits in
the UI is immediately what the agents see.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

Phase = Literal["intake", "analysis", "drafting", "review", "awaiting_approval", "filing", "tracking", "referred"]
Trigger = Literal["message", "generate_documents", "approval_decided", "filing_update", "refresh_analysis"]


class SlotValue(TypedDict, total=False):
    fact_id: str
    value: str
    provenance: str
    excerpt: str | None
    confirmed: bool


class CaseState(TypedDict, total=False):
    # identity
    case_id: str
    user_id: str
    workflow_id: str
    language: str
    allow_external_ai: bool
    today: str
    # input for this run
    trigger: Trigger
    message: str | None
    message_id: str | None
    modality: str
    payload: dict[str, Any]
    # durable context
    phase: Phase
    slots: dict[str, SlotValue]
    asked_slot: str | None
    skipped_slots: list[str]
    slot_attempts: dict[str, int]
    batch_pending: list[str]
    batch_declined: bool
    turns: int
    category: str | None
    category_confidence: float | None
    routing: dict[str, Any]
    rule_outcomes: dict[str, Any]
    research_topics: list[str]
    citations: list[dict[str, Any]]
    plan: list[dict[str, Any]]
    documents: dict[str, Any]
    verification: dict[str, Any]
    approval: dict[str, Any]
    safety: dict[str, Any]
    # output of this run
    reply: str | None
    reply_cards: list[dict[str, Any]]
    next_question: str | None
    events: list[dict[str, Any]]
    errors: list[dict[str, Any]]


DURABLE_KEYS = (
    "phase", "asked_slot", "skipped_slots", "slot_attempts", "batch_pending", "batch_declined", "turns", "category", "category_confidence",
    "routing", "rule_outcomes", "research_topics", "citations", "plan", "documents",
    "verification", "approval", "safety", "language",
)


def durable(state: CaseState) -> dict[str, Any]:
    """The subset of state persisted in workflow_instances.state between runs."""
    return {k: state.get(k) for k in DURABLE_KEYS if k in state}


def new_state(case_id: str, user_id: str, workflow_id: str, language: str) -> CaseState:
    return CaseState(
        case_id=case_id, user_id=user_id, workflow_id=workflow_id, language=language,
        phase="intake", slots={}, asked_slot=None, skipped_slots=[], turns=0, category=None,
        category_confidence=None, routing={}, rule_outcomes={}, research_topics=[], citations=[],
        plan=[], documents={}, verification={}, approval={}, safety={}, events=[], errors=[],
        reply_cards=[],
    )
