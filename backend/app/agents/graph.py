"""LangGraph orchestration of the consumer-dispute workflow.

Graph (one run per trigger):

    START ─┬─ message ──────────► safety ─► intake ─► classify ─┬─► referral ─► END
           │                                                    ├─► ask ─► END            (missing facts)
           │                                                    └─► research ─► plan ─► END
           ├─ refresh_analysis ─► research ─► plan ─► END
           ├─ generate_documents ► documents ─► END              (verification runs per version)
           ├─ approval_decided ──► filing ─► END                 (human approval interrupt resumes here)
           └─ filing_update ─────► tracking ─► END

Persistence: the durable part of the state is checkpointed to `workflow_instances`
after each run (with an optimistic revision counter), and facts live in `case_facts`.
A run can therefore resume after a crash, a network drop or a pause for approval.
Every node execution is recorded in `agent_executions`.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import classification as classification_agent
from app.agents import intake as intake_agent
from app.agents import planning as planning_agent
from app.agents import research as research_agent
from app.agents import responder
from app.agents.extract import URGENT_SAFETY
from app.agents.llm import LLMProvider, get_llm
from app.agents.state import CaseState, durable, new_state
from app.core.errors import ConflictError
from app.domains.consumer.slots import SLOT_BY_KEY, SLOTS
from app.models import AgentExecution, Approval, Case, GeneratedDocument, User, WorkflowInstance
from app.models.enums import ApprovalAction, ApprovalStatus, CaseStatus, FactProvenance, FactStatus, WorkflowStatus
from app.services import facts as fact_service
from app.services.documents import generate_documents

logger = logging.getLogger(__name__)

CORE_DOCUMENTS = ("consumer_complaint", "memo_of_parties", "list_of_dates", "evidence_index")
BATCH_SLOT = "__confirm_batch__"


def _ctx(config: RunnableConfig) -> tuple[AsyncSession, LLMProvider, WorkflowInstance, Case]:
    c = config["configurable"]
    return c["db"], c["llm"], c["workflow"], c["case"]


def recorded(agent: str) -> Callable[[Callable[..., Awaitable[dict[str, Any]]]], Callable[..., Awaitable[dict[str, Any]]]]:
    """Record each node run in agent_executions, retry once, and degrade gracefully."""

    def wrap(fn: Callable[..., Awaitable[dict[str, Any]]]) -> Callable[..., Awaitable[dict[str, Any]]]:
        async def node(state: CaseState, config: RunnableConfig) -> dict[str, Any]:
            db, llm, workflow, case = _ctx(config)
            last_error: Exception | None = None
            for attempt in (1, 2):
                started = time.perf_counter()
                try:
                    async with db.begin_nested():
                        update_ = await fn(state, config)
                    db.add(AgentExecution(
                        workflow_id=workflow.id, case_id=case.id, agent=agent, status="succeeded",
                        provider=update_.pop("_provider", "rules"), model=update_.pop("_model", None),
                        attempt=attempt, latency_ms=int((time.perf_counter() - started) * 1000),
                        summary=update_.pop("_summary", {}),
                    ))
                    return update_
                except Exception as exc:  # noqa: BLE001 - recorded and surfaced below
                    last_error = exc
                    logger.exception("Agent %s failed (attempt %s)", agent, attempt)
                    db.add(AgentExecution(
                        workflow_id=workflow.id, case_id=case.id, agent=agent, status="failed", provider="n/a",
                        attempt=attempt, latency_ms=int((time.perf_counter() - started) * 1000),
                        error=f"{type(exc).__name__}: {str(exc)[:500]}",
                    ))
            lang = responder.L(state.get("language", "en"))
            message = ("माफ़ कीजिए, इस कदम में तकनीकी दिक्कत आई। आपकी जानकारी सुरक्षित है — कृपया थोड़ी देर बाद फिर कोशिश करें।"
                       if lang == "hi" else
                       "Sorry, something went wrong in this step. Your information is saved — please try again shortly.")
            return {
                "reply": message,
                "errors": [*state.get("errors", []), {"agent": agent, "error": type(last_error).__name__}],
            }

        node.__name__ = fn.__name__
        return node

    return wrap


def _event(state: CaseState, kind: str, **data: Any) -> list[dict[str, Any]]:
    return [*state.get("events", []), {"type": kind, **data}]


# ---- nodes -------------------------------------------------------------------------------------


@recorded("safety")
async def safety_node(state: CaseState, config: RunnableConfig) -> dict[str, Any]:
    message = state.get("message") or ""
    if URGENT_SAFETY.search(message):
        text, cards = responder.safety_reply(intake_agent.detect_language(message, state.get("language", "en")))
        return {"reply": text, "reply_cards": cards, "safety": {"urgent": True},
                "_summary": {"urgent": True}}
    return {"safety": {"urgent": False}, "_summary": {"urgent": False}}


@recorded("intake")
async def intake_node(state: CaseState, config: RunnableConfig) -> dict[str, Any]:
    db, llm, _workflow, case = _ctx(config)
    message = state.get("message") or ""
    today = date.fromisoformat(state["today"])
    asked = state.get("asked_slot")
    slots = state.get("slots", {})
    batch_declined = bool(state.get("batch_declined"))
    noted: list[str] = []

    if asked == BATCH_SLOT:
        # We asked the user to confirm several inferred facts at once.
        from app.agents.extract import yes_no

        answer = yes_no(message)
        if answer is True:
            for key in state.get("batch_pending", []):
                slot = slots.get(key)
                if slot and slot.get("provenance") == FactProvenance.AI_INFERENCE:
                    await fact_service.upsert_fact(db, case.id, key, slot["value"], FactProvenance.USER_CONFIRMED,
                                                   value_type=SLOT_BY_KEY[key].value_type, excerpt=slot.get("excerpt"),
                                                   source_type="message", source_id=state.get("message_id"))
                    noted.append(key)
        else:
            batch_declined = True
        asked = None

    result, fallback = await intake_agent.run_intake(
        llm, state.get("allow_external_ai", False), message, asked, slots, today, state.get("language", "en"))

    attempts = dict(state.get("slot_attempts", {}))
    if asked and asked in SLOT_BY_KEY:
        answered = any(c.key == asked for c in result.facts) or result.confirmation is not None \
            or result.skipped_slot == asked
        attempts[asked] = 0 if answered else attempts.get(asked, 0) + 1

    for cand in result.facts:
        fact = await fact_service.upsert_fact(
            db, case.id, cand.key, cand.value, cand.provenance, value_type=cand.value_type,
            excerpt=cand.excerpt, source_type="message", source_id=state.get("message_id"),
            confidence=cand.confidence,
        )
        if fact is not None:
            noted.append(cand.key)
    if result.confirmation is False and asked and asked in slots:
        # The user rejected our inferred value: retire it and ask the question plainly.
        from app.models import CaseFact

        fact_id = slots[asked].get("fact_id")
        if fact_id:
            fact = await db.get(CaseFact, uuid.UUID(fact_id))
            if fact is not None and fact.provenance == FactProvenance.AI_INFERENCE:
                fact.status = FactStatus.REJECTED
    skipped = list(state.get("skipped_slots", []))
    if result.skipped_slot and result.skipped_slot not in skipped:
        skipped.append(result.skipped_slot)
    # After three unsuccessful attempts, stop asking; the slot stays visibly missing in the case file.
    for key, count in attempts.items():
        if count >= 3 and key not in skipped:
            skipped.append(key)
    await fact_service.sync_case_columns(db, case)
    new_slots = await fact_service.load_slots(db, case.id)
    language = result.language if result.language in ("en", "hi") else state.get("language", "en")
    return {
        "slots": new_slots, "skipped_slots": skipped, "language": language, "slot_attempts": attempts,
        "batch_declined": batch_declined,
        "turns": state.get("turns", 0) + 1,
        "payload": {**state.get("payload", {}), "tone": result.tone, "is_question": result.is_question,
                    "noted": noted, "rejected": result.confirmation is False},
        "events": _event(state, "facts_updated", keys=noted),
        "_provider": result.method if result.method == "rules" else llm.name,
        "_model": None if result.method == "rules" else llm.model,
        "_summary": {"noted": noted, "method": result.method, "llm_fallback": fallback,
                     "skipped": result.skipped_slot},
    }


@recorded("classification")
async def classify_node(state: CaseState, config: RunnableConfig) -> dict[str, Any]:
    _db, llm, _workflow, case = _ctx(config)
    grievance = state.get("slots", {}).get("grievance", {}).get("value") or state.get("message") or ""
    result = await classification_agent.classify(llm, state.get("allow_external_ai", False), grievance)
    routing = {"supported": result.supported, "reasons": result.reasons, "secondary": result.secondary,
               "signals": result.signals, "method": result.method}
    if result.category != "unclear":
        case.category = result.category
        case.classification_confidence = result.confidence
    case.requires_human_review = (not result.supported) or result.confidence < 0.6
    return {
        "category": result.category, "category_confidence": result.confidence, "routing": routing,
        "_provider": result.method if result.method == "rules" else llm.name,
        "_summary": {"category": result.category, "confidence": result.confidence},
    }


@recorded("referral")
async def referral_node(state: CaseState, config: RunnableConfig) -> dict[str, Any]:
    _db, _llm, _workflow, case = _ctx(config)
    category = state.get("category") or "other"
    text, cards = responder.referral_reply(state.get("language", "en"), category, state.get("routing", {}).get("reasons", []))
    case.status = CaseStatus.NEEDS_PROFESSIONAL_REVIEW
    return {"reply": text, "reply_cards": cards, "phase": "referred", "asked_slot": None,
            "_summary": {"category": category}}


@recorded("intake_question")
async def ask_node(state: CaseState, config: RunnableConfig) -> dict[str, Any]:
    db, llm, _workflow, _case = _ctx(config)
    slots = state.get("slots", {})
    payload = state.get("payload", {})
    lang = state.get("language", "en")
    answer_text: str | None = None
    answer_cards: list[dict[str, Any]] = []
    message = state.get("message")
    if payload.get("is_question") and message:
        answer_text, answer_cards = await responder.answer_question(db, message, lang, state.get("rule_outcomes", {}))

    skipped = state.get("skipped_slots", [])
    pending_inferences = [
        s.key for s in SLOTS
        if s.key in slots and slots[s.key].get("provenance") == FactProvenance.AI_INFERENCE and s.key not in skipped
    ]
    batch: list[str] = []
    slot_key: str | None
    question: str | None
    if len(pending_inferences) >= 2 and not state.get("batch_declined"):
        batch = pending_inferences
        slot_key, is_confirm = BATCH_SLOT, True
        question = responder.batch_confirmation(batch, slots, lang)
    else:
        slot_key, is_confirm = intake_agent.next_slot(slots, skipped)
        asked_before = slot_key == state.get("asked_slot")
        retry = asked_before and state.get("slot_attempts", {}).get(slot_key or "", 0) > 0
        question = None
        if slot_key:
            confirm_value = slots[slot_key]["value"] if is_confirm else None
            question = responder.question_for(slot_key, lang, confirm_value, first_time=not asked_before,
                                              retry=retry and not is_confirm)
    draft = responder.intake_reply(lang, state.get("turns", 0), payload.get("tone", "calm"), question,
                                   payload.get("noted", []), is_first=state.get("turns", 0) <= 1)
    if answer_text:
        draft = f"{answer_text} {question or ''}".strip()
    text, used_llm = await responder.polish(
        llm, state.get("allow_external_ai", False), draft, lang, question,
        {c.get("section_ref", "") for c in state.get("citations", [])}, state.get("modality") == "voice")
    cards = list(answer_cards)
    if slot_key == BATCH_SLOT:
        cards.append({"type": "confirm_facts", "keys": batch,
                      "items": [{"key": k, "value": slots[k]["value"], "fact_id": slots[k].get("fact_id")} for k in batch]})
    elif slot_key:
        slot = SLOT_BY_KEY[slot_key]
        cards.append({"type": "question", "slot": slot_key, "confirm": is_confirm, "value_type": slot.value_type,
                      "label": slot.label_hi if lang == "hi" else slot.label_en})
    missing = intake_agent.missing_required(slots)
    return {
        "reply": text, "reply_cards": cards, "asked_slot": slot_key, "next_question": question,
        "batch_pending": batch,
        "phase": "intake" if missing else state.get("phase", "intake"),
        "_provider": "anthropic" if used_llm else "rules",
        "_summary": {"asked": slot_key, "confirm": is_confirm, "missing_required": missing},
    }


@recorded("legal_research")
async def research_node(state: CaseState, config: RunnableConfig) -> dict[str, Any]:
    db, llm, _workflow, case = _ctx(config)
    today = date.fromisoformat(state["today"])
    outcomes = await research_agent.compute_rule_outcomes(db, state.get("slots", {}), today)
    citations = await research_agent.research_case(db, llm, state.get("allow_external_ai", False), case.id,
                                                   state.get("language", "en"))
    status = (outcomes.get("consumer_status") or {}).get("value", {}).get("status")
    case.analysis = {
        **(case.analysis or {}),
        "rule_outcomes": outcomes,
        "missing_information": intake_agent.missing_required(state.get("slots", {})),
        "potential_routes": _routes(outcomes),
    }
    grounded = sum(1 for o in outcomes.values() if o.get("grounded"))
    return {
        "rule_outcomes": outcomes, "citations": citations, "research_topics": list(research_agent.TOPICS),
        "phase": "referred" if status == "may_not_be_consumer" else "analysis",
        "_summary": {"outcomes": list(outcomes), "grounded": grounded, "citations": len(citations)},
    }


def _routes(outcomes: dict[str, Any]) -> list[dict[str, Any]]:
    routes = [{
        "key": "consumer_commission", "title_en": "Complaint to the Consumer Commission (e-Jagriti)",
        "title_hi": "उपभोक्ता आयोग में शिकायत (ई-जागृति)",
        "forum": (outcomes.get("pecuniary_forum") or {}).get("value"),
        "basis": ["cpa_2019:Section 35"],
    }, {
        "key": "national_consumer_helpline", "title_en": "Pre-litigation help via National Consumer Helpline (1915)",
        "title_hi": "राष्ट्रीय उपभोक्ता हेल्पलाइन (1915) से मुकदमे से पहले सहायता",
        "basis": [], "optional": True,
    }]
    if (outcomes.get("consumer_status") or {}).get("value", {}).get("status") == "may_not_be_consumer":
        routes.insert(0, {"key": "professional_advice", "title_en": "Get advice from a lawyer or free legal aid",
                          "title_hi": "वकील या मुफ़्त कानूनी सहायता से सलाह लें", "basis": ["cpa_2019:Section 2(7)"]})
    return routes


@recorded("workflow_planning")
async def plan_node(state: CaseState, config: RunnableConfig) -> dict[str, Any]:
    db, llm, workflow, case = _ctx(config)
    outcomes = state.get("rule_outcomes", {})
    phase = state.get("phase", "analysis")
    plan = planning_agent.build_plan(outcomes, state.get("slots", {}), phase)
    await planning_agent.persist_plan(db, workflow.id, plan)
    await planning_agent.sync_limitation_deadline(db, case.id, outcomes)
    lang = state.get("language", "en")
    if phase == "referred":
        text, cards = responder.referral_reply(lang, "not_consumer",
                                               [(outcomes.get("consumer_status") or {}).get("explanation_en", "")])
        case.status = CaseStatus.NEEDS_PROFESSIONAL_REVIEW
    else:
        text, cards = responder.analysis_reply(lang, outcomes)
        if case.status in (CaseStatus.INTAKE, CaseStatus.RESEARCH):
            case.status = CaseStatus.PLANNING
        if state.get("trigger") == "refresh_analysis" or state.get("phase") != "analysis":
            pass
    # A question the user asked in the same message is answered first.
    payload = state.get("payload", {})
    message = state.get("message")
    if payload.get("is_question") and message:
        answer, answer_cards = await responder.answer_question(db, message, lang, outcomes)
        text = f"{answer} {text}"
        cards = answer_cards + cards
    allowed = {c.get("section_ref", "") for c in state.get("citations", [])}
    allowed |= {b["section_ref"] for o in outcomes.values() for b in o.get("basis", [])}
    polished, used = await responder.polish(llm, state.get("allow_external_ai", False), text, lang, None, allowed,
                                            state.get("modality") == "voice")
    return {"plan": plan, "reply": polished, "reply_cards": cards, "asked_slot": None,
            "_provider": "anthropic" if used else "rules", "_summary": {"steps": len(plan)}}


@recorded("document_generation")
async def documents_node(state: CaseState, config: RunnableConfig) -> dict[str, Any]:
    db, _llm, _workflow, case = _ctx(config)
    lang = responder.L(state.get("language", "en"))
    missing = intake_agent.missing_required(state.get("slots", {}))
    if not state.get("rule_outcomes"):
        missing = missing or ["analysis"]
    if missing:
        labels = [SLOT_BY_KEY[k].label_hi if lang == "hi" else SLOT_BY_KEY[k].label_en for k in missing if k in SLOT_BY_KEY]
        text = ("दस्तावेज़ बनाने से पहले कुछ जानकारी चाहिए या आपकी पुष्टि बाकी है: " if lang == "hi"
                else "Before I can prepare documents I still need, or need you to confirm: ") + ", ".join(labels) + "."
        return {"reply": text, "reply_cards": [{"type": "missing_facts", "keys": missing}],
                "_summary": {"blocked": missing}}
    today = date.fromisoformat(state["today"])
    results = await generate_documents(db, case.id, state.get("rule_outcomes", {}), state.get("citations", []), today)
    blocked = [r["doc_type"] for r in results if r["validation"]["status"] == "blocked"]
    case.status = CaseStatus.REVIEW
    text = ("मैंने आपके ड्राफ़्ट तैयार कर दिए हैं। कृपया हर दस्तावेज़ ध्यान से पढ़ें, ज़रूरत हो तो सुधारें, और फिर स्वीकृत करें।"
            if lang == "hi" else
            "I've prepared your drafts. Please read each document carefully, correct anything that's wrong, and then approve it.")
    if blocked:
        text += (" कुछ दस्तावेज़ों में अभी ज़रूरी जानकारी बाकी है।" if lang == "hi"
                 else " Some documents still have missing details that must be fixed before approval.")
    return {"documents": {r["doc_type"]: r for r in results}, "phase": "review", "reply": text,
            "verification": {r["doc_type"]: r["validation"]["status"] for r in results},
            "reply_cards": [{"type": "documents", "items": results}],
            "_summary": {"generated": [r["doc_type"] for r in results if r["changed"]], "blocked": blocked}}


@recorded("filing")
async def filing_node(state: CaseState, config: RunnableConfig) -> dict[str, Any]:
    db, _llm, _workflow, case = _ctx(config)
    lang = responder.L(state.get("language", "en"))
    docs = (await db.scalars(select(GeneratedDocument).where(
        GeneratedDocument.case_id == case.id, GeneratedDocument.doc_type.in_(CORE_DOCUMENTS)))).all()
    approved = {d.doc_type for d in docs if d.status == "approved"}
    pending = [d for d in CORE_DOCUMENTS if d not in approved]
    if pending:
        return {"phase": "awaiting_approval", "approval": {"pending_documents": pending},
                "reply": ("कुछ दस्तावेज़ों की स्वीकृति अभी बाकी है।" if lang == "hi" else
                          "Some documents still need your approval before filing."),
                "_summary": {"pending": pending}}
    case.status = CaseStatus.READY_TO_FILE
    text = ("सभी दस्तावेज़ स्वीकृत हैं। अब आप ई-जागृति पर शिकायत दर्ज कर सकते हैं — मैं हर कदम पर मार्गदर्शन करूँगी। लॉग-इन, OTP "
            "और CAPTCHA आप खुद भरेंगे, और जमा करने का अंतिम बटन भी आप ही दबाएँगे।" if lang == "hi" else
            "All documents are approved. You can now file on e-Jagriti and I'll guide you through each step. You "
            "complete login, OTP and CAPTCHA yourself, and you press the final submit button.")
    return {"phase": "filing", "reply": text, "approval": {"pending_documents": []},
            "reply_cards": [{"type": "filing_ready"}], "_summary": {"ready": True}}


@recorded("case_tracking")
async def tracking_node(state: CaseState, config: RunnableConfig) -> dict[str, Any]:
    db, _llm, workflow, case = _ctx(config)
    lang = responder.L(state.get("language", "en"))
    plan = planning_agent.build_plan(state.get("rule_outcomes", {}), state.get("slots", {}), "tracking")
    await planning_agent.persist_plan(db, workflow.id, plan)
    text = ("फाइलिंग की जानकारी दर्ज कर ली गई है। यह आपकी दी गई जानकारी है; आधिकारिक स्थिति के लिए ई-जागृति पोर्टल देखें।"
            if lang == "hi" else
            "Filing details recorded. This is the information you reported; check the e-Jagriti portal for the official status.")
    return {"phase": "tracking", "plan": plan, "reply": text, "_summary": {"status": case.status}}


# ---- routing -------------------------------------------------------------------------------------


def route_trigger(state: CaseState) -> str:
    return {
        "message": "safety", "generate_documents": "documents", "approval_decided": "filing",
        "filing_update": "tracking", "refresh_analysis": "research",
    }[state["trigger"]]


def after_safety(state: CaseState) -> str:
    return END if state.get("safety", {}).get("urgent") else "intake"


def after_intake(state: CaseState) -> str:
    slots = state.get("slots", {})
    if "grievance" not in slots:
        return "ask"
    needs_classification = state.get("category") in (None, "unclear") or state.get("turns", 0) <= 2 or \
        "grievance" in state.get("payload", {}).get("noted", [])
    return "classify" if needs_classification else after_classify(state)


def after_classify(state: CaseState) -> str:
    category = state.get("category")
    routing = state.get("routing", {})
    if category not in (None, "unclear", "consumer_dispute") and not routing.get("supported", True):
        return "referral"
    if intake_agent.missing_required(state.get("slots", {})):
        return "ask"
    noted = state.get("payload", {}).get("noted", [])
    already_analysed = state.get("phase") in ("analysis", "drafting", "review", "awaiting_approval", "filing", "tracking")
    if already_analysed and not noted:
        return "ask"
    return "research"


def build_graph() -> Any:
    graph = StateGraph(CaseState)
    graph.add_node("safety", safety_node)
    graph.add_node("intake", intake_node)
    graph.add_node("classify", classify_node)
    graph.add_node("referral", referral_node)
    graph.add_node("ask", ask_node)
    graph.add_node("research", research_node)
    graph.add_node("plan", plan_node)
    graph.add_node("documents", documents_node)
    graph.add_node("filing", filing_node)
    graph.add_node("tracking", tracking_node)
    graph.add_conditional_edges(START, route_trigger, ["safety", "documents", "filing", "tracking", "research"])
    graph.add_conditional_edges("safety", after_safety, ["intake", END])
    graph.add_conditional_edges("intake", after_intake, ["classify", "ask", "referral", "research"])
    graph.add_conditional_edges("classify", after_classify, ["referral", "ask", "research"])
    graph.add_edge("research", "plan")
    for node in ("referral", "ask", "plan", "documents", "filing", "tracking"):
        graph.add_edge(node, END)
    return graph.compile()


_GRAPH = None


def get_graph() -> Any:
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


# ---- runner --------------------------------------------------------------------------------------


@dataclass
class RunResult:
    reply: str | None
    cards: list[dict[str, Any]] = field(default_factory=list)
    phase: str | None = None
    asked_slot: str | None = None
    language: str = "en"
    events: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)


async def get_or_create_workflow(db: AsyncSession, case: Case) -> WorkflowInstance:
    workflow = await db.scalar(select(WorkflowInstance).where(WorkflowInstance.case_id == case.id))
    if workflow is None:
        workflow = WorkflowInstance(case_id=case.id, workflow_type="consumer_dispute", status=WorkflowStatus.WAITING_USER,
                                    state={}, revision=0)
        db.add(workflow)
        await db.flush()
    return workflow


async def run_case_workflow(
    db: AsyncSession, case: Case, user: User, trigger: str, *, message: str | None = None,
    message_id: str | None = None, modality: str = "text", payload: dict[str, Any] | None = None,
    llm: LLMProvider | None = None, today: date | None = None,
) -> RunResult:
    llm = llm or get_llm()
    workflow = await get_or_create_workflow(db, case)
    revision = workflow.revision
    prefs = user.preferences
    state = new_state(str(case.id), str(user.id), str(workflow.id), case.language)
    state.update(workflow.state or {})  # type: ignore[typeddict-item]
    state["slots"] = await fact_service.load_slots(db, case.id)
    state["allow_external_ai"] = bool(prefs and prefs.consent_external_ai and llm.available)
    state["today"] = (today or date.today()).isoformat()
    state["trigger"] = trigger  # type: ignore[typeddict-item]
    state["message"] = message
    state["message_id"] = message_id
    state["modality"] = modality
    state["payload"] = payload or {}
    state["reply"] = None
    state["reply_cards"] = []
    state["events"] = []
    state["errors"] = []

    config: RunnableConfig = {"configurable": {"db": db, "llm": llm, "workflow": workflow, "case": case}}
    workflow.status = WorkflowStatus.RUNNING
    final: CaseState = await get_graph().ainvoke(state, config=config)

    phase = final.get("phase", "intake")
    workflow.state = durable(final)
    workflow.current_node = trigger
    workflow.status = {
        "awaiting_approval": WorkflowStatus.WAITING_APPROVAL, "review": WorkflowStatus.WAITING_APPROVAL,
        "tracking": WorkflowStatus.WAITING_USER, "referred": WorkflowStatus.WAITING_USER,
    }.get(phase, WorkflowStatus.WAITING_USER)
    workflow.last_error = final["errors"][-1]["error"] if final.get("errors") else None
    # Optimistic concurrency: fail if another run checkpointed in the meantime.
    result = await db.execute(
        update(WorkflowInstance)
        .where(WorkflowInstance.id == workflow.id, WorkflowInstance.revision == revision)
        .values(revision=revision + 1)
        .execution_options(synchronize_session=False)
    )
    if getattr(result, "rowcount", 1) != 1:
        raise ConflictError("This case was updated in another window. Please reload.", code="workflow_conflict")
    workflow.revision = revision + 1
    if final.get("language") in ("en", "hi"):
        case.language = final["language"]
    return RunResult(
        reply=final.get("reply"), cards=final.get("reply_cards", []), phase=phase,
        asked_slot=final.get("asked_slot"), language=final.get("language", "en"),
        events=final.get("events", []), errors=final.get("errors", []),
    )


async def pending_document_approvals(db: AsyncSession, case_id: uuid.UUID) -> list[Approval]:
    return list((await db.scalars(select(Approval).where(
        Approval.case_id == case_id, Approval.action == ApprovalAction.APPROVE_DOCUMENT,
        Approval.status == ApprovalStatus.PENDING))).all())
