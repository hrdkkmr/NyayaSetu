"""Agent workflow tests: intake, classification, grounding, escalation, recovery and LLM safeguards."""

from __future__ import annotations

import httpx
from sqlalchemy import select

from app.agents.classification import LLMClassification
from app.agents.intake import LLMFact, LLMIntake
from app.agents.llm import LLMUnavailableError, set_llm
from app.agents.responder import Polished
from app.db.session import session_scope
from app.models import AgentExecution, CaseFact, WorkflowInstance
from tests.conftest import Session, register
from tests.fakes import ScriptedProvider

LAPTOP_STORY = [
    "I bought a laptop from Amazon on 12 March 2026 for Rs. 54,999 but it was delivered damaged and the seller "
    "is refusing to replace it",
    "yes",
    "it arrived broken on 15 March 2026",
    "Yes, I emailed them on 16 March and they refused",
    "replacement or a refund",
    "invoice, order confirmation and photos",
    "Pune, Maharashtra",
    "for my own personal use",
    "Shop No. 4, Example Market, Pune",
    "Asha Verma",
    "12 MG Road, Pune 411001",
]


async def run_story(s: Session, messages: list[str], language: str = "en") -> tuple[str, list[dict]]:
    case = (await s.post("/cases", json={"language": language})).json()["case"]
    turns = []
    for text in messages:
        resp = await s.post(f"/cases/{case['id']}/messages", json={"text": text})
        assert resp.status_code == 200, resp.text
        turns.append(resp.json())
    return case["id"], turns


async def test_full_offline_intake_reaches_grounded_analysis(client: httpx.AsyncClient) -> None:
    s = await register(client)
    case_id, turns = await run_story(s, LAPTOP_STORY)
    first = turns[0]["assistant_message"]
    assert first["cards"][0]["type"] == "confirm_facts"  # inferred facts are confirmed, not assumed
    assert turns[-1]["phase"] == "analysis"
    final = turns[-1]["assistant_message"]["content"]
    assert "District Commission" in final and "No filing fee" in final and "15 March 2028" in final
    assert "not advice from a lawyer" in final
    detail = (await s.get(f"/cases/{case_id}")).json()
    assert detail["missing_information"] == []
    outcomes = detail["analysis"]["rule_outcomes"]
    assert all(o["grounded"] for o in outcomes.values())
    assert outcomes["pecuniary_forum"]["basis"][0]["source_url"]
    assert any(d["kind"] == "limitation" and d["is_estimate"] for d in detail["deadlines"])
    research = (await s.get(f"/cases/{case_id}/research")).json()
    refs = {c["section_ref"] for c in research["citations"]}
    assert {"Section 69", "Rule 3"} <= refs
    for c in research["citations"]:
        assert c["document"]["source_url"].startswith("https://")


async def test_one_question_per_turn(client: httpx.AsyncClient) -> None:
    s = await register(client)
    _, turns = await run_story(s, LAPTOP_STORY[:6])
    for turn in turns[1:]:
        text = turn["assistant_message"]["content"]
        assert text.count("?") <= 1, text


async def test_unparseable_answer_gets_a_hint_then_is_skipped(client: httpx.AsyncClient) -> None:
    s = await register(client)
    case_id, turns = await run_story(s, LAPTOP_STORY[:2] + ["they ignored me"])
    assert "didn't quite catch" in turns[-1]["assistant_message"]["content"]
    for _ in range(3):
        last = await s.post(f"/cases/{case_id}/messages", json={"text": "they ignored me"})
    assert last.json()["asked_slot"] != "problem_date"


async def test_inferences_are_not_promoted_without_confirmation(client: httpx.AsyncClient) -> None:
    s = await register(client)
    case_id, _ = await run_story(s, LAPTOP_STORY[:1])
    async with session_scope() as db:
        facts = (await db.scalars(select(CaseFact).where(CaseFact.case_id == case_id))).all()
    by_key = {f.key: f.provenance for f in facts}
    assert by_key["seller_name"] == "ai_inference"
    assert by_key["grievance"] == "user_stated"
    # Declining the batch confirmation keeps them unconfirmed.
    await s.post(f"/cases/{case_id}/messages", json={"text": "no"})
    async with session_scope() as db:
        seller = (await db.scalars(select(CaseFact).where(CaseFact.case_id == case_id,
                                                          CaseFact.key == "seller_name"))).all()
    assert all(f.provenance == "ai_inference" for f in seller)


async def test_hindi_conversation(client: httpx.AsyncClient) -> None:
    s = await register(client, language="hi")
    case_id, turns = await run_story(s, [
        "मैंने 5 जून 2026 को दुकान से 18000 रुपये का फ्रिज खरीदा था, दो हफ्ते में ही खराब हो गया और दुकानदार ठीक नहीं कर रहा",
        "हाँ",
    ], language="hi")
    assert turns[0]["language"] == "hi"
    assert "क्या ये सब सही हैं" in turns[0]["assistant_message"]["content"]
    assert turns[1]["asked_slot"] == "seller_name"
    question = await s.post(f"/cases/{case_id}/messages", json={"text": "शिकायत करने की समय सीमा क्या है?"})
    assert "धारा 69" in question.json()["assistant_message"]["content"]


async def test_non_consumer_matter_is_referred(client: httpx.AsyncClient) -> None:
    s = await register(client)
    case_id, turns = await run_story(s, ["My neighbour assaulted me and threatened me, the police refused to file an FIR"])
    reply = turns[0]["assistant_message"]
    assert turns[0]["phase"] == "referred"
    assert "15100" in reply["content"] and "112" in reply["content"]
    detail = (await s.get(f"/cases/{case_id}")).json()
    assert detail["case"]["status"] == "needs_professional_review"
    assert detail["case"]["requires_human_review"] is True


async def test_commercial_purchase_is_flagged(client: httpx.AsyncClient) -> None:
    s = await register(client)
    story = list(LAPTOP_STORY)
    story[7] = "for resale in my business"
    case_id, turns = await run_story(s, story)
    assert turns[-1]["phase"] == "referred"
    detail = (await s.get(f"/cases/{case_id}")).json()
    assert detail["analysis"]["rule_outcomes"]["consumer_status"]["value"]["status"] == "may_not_be_consumer"


async def test_urgent_safety_message(client: httpx.AsyncClient) -> None:
    s = await register(client)
    _, turns = await run_story(s, ["My husband is threatening to kill me tonight"])
    assert "112" in turns[0]["assistant_message"]["content"]


async def test_workflow_persists_and_resumes(client: httpx.AsyncClient) -> None:
    s = await register(client)
    case_id, _ = await run_story(s, LAPTOP_STORY[:3])
    async with session_scope() as db:
        wf = await db.scalar(select(WorkflowInstance).where(WorkflowInstance.case_id == case_id))
        assert wf.revision == 3 and wf.state["asked_slot"]
        asked = wf.state["asked_slot"]
        executions = (await db.scalars(select(AgentExecution).where(AgentExecution.case_id == case_id))).all()
    assert {"intake", "classification", "intake_question"} <= {e.agent for e in executions}
    # A fresh client session (e.g. after a reconnect) continues from the checkpoint.
    messages = (await s.get(f"/cases/{case_id}/messages")).json()
    assert messages["asked_slot"] == asked


async def test_failed_agent_is_recorded_and_degrades_gracefully(client: httpx.AsyncClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.agents import graph

    async def boom(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("simulated tool failure")

    monkeypatch.setattr(graph.classification_agent, "classify", boom)
    s = await register(client)
    case_id, turns = await run_story(s, LAPTOP_STORY[:1])
    assert turns[0]["errors"] and turns[0]["errors"][0]["agent"] == "classification"
    async with session_scope() as db:
        failed = (await db.scalars(select(AgentExecution).where(AgentExecution.case_id == case_id,
                                                                AgentExecution.status == "failed"))).all()
    assert len(failed) == 2  # one retry


# ---- LLM path (scripted provider, user consented to external AI) --------------------------------


async def _consent_ai(s: Session) -> None:
    r = await s.patch("/users/me/preferences", json={"consent_external_ai": True})
    assert r.status_code == 200


async def test_llm_not_used_without_consent(client: httpx.AsyncClient) -> None:
    provider = ScriptedProvider({})
    set_llm(provider)
    s = await register(client)
    await run_story(s, LAPTOP_STORY[:1])
    assert provider.calls == []


async def test_llm_excerpts_are_validated(client: httpx.AsyncClient) -> None:
    provider = ScriptedProvider({
        "LLMIntake": LLMIntake(
            facts=[
                LLMFact(slot="grievance", value="Laptop delivered damaged", excerpt="delivered damaged", is_inference=False),
                LLMFact(slot="amount_paid", value="54999", excerpt="Rs. 54,999", is_inference=False),
                # Fabricated: the user never said this.
                LLMFact(slot="seller_address", value="1 Fake Street", excerpt="1 Fake Street", is_inference=False),
            ],
            language="en", tone="calm", is_question=False, answered_asked_slot=False),
        "LLMClassification": LLMClassification(category="consumer_dispute", confidence=0.9, reasons=["bought goods"]),
        "Polished": Polished(reply="Thanks for explaining. Under Section 99 you will definitely win. What did you buy?"),
    })
    set_llm(provider)
    s = await register(client)
    await _consent_ai(s)
    case_id, turns = await run_story(s, ["The laptop was delivered damaged, I paid Rs. 54,999"])
    async with session_scope() as db:
        facts = {f.key: f for f in (await db.scalars(select(CaseFact).where(CaseFact.case_id == case_id))).all()}
    assert facts["amount_paid"].provenance == "user_stated"
    assert facts["seller_address"].provenance == "ai_inference"  # unsupported excerpt is downgraded
    reply = turns[0]["assistant_message"]["content"]
    assert "Section 99" not in reply and "definitely win" not in reply  # unsafe rephrasing rejected


async def test_llm_failure_falls_back_to_rules(client: httpx.AsyncClient) -> None:
    provider = ScriptedProvider({"LLMIntake": LLMUnavailableError("down"), "LLMClassification": LLMUnavailableError("down"),
                                 "Polished": LLMUnavailableError("down")})
    set_llm(provider)
    s = await register(client)
    await _consent_ai(s)
    _, turns = await run_story(s, LAPTOP_STORY[:1])
    assert turns[0]["assistant_message"]["cards"][0]["type"] == "confirm_facts"
    assert turns[0]["errors"] == []


async def test_llm_cannot_override_strong_criminal_signals(client: httpx.AsyncClient) -> None:
    set_llm(ScriptedProvider({
        "LLMClassification": LLMClassification(category="consumer_dispute", confidence=0.95, reasons=["x"]),
    }))
    s = await register(client)
    await _consent_ai(s)
    _, turns = await run_story(s, ["The shopkeeper assaulted me and threatened me, police refused FIR"])
    assert turns[0]["phase"] == "referred"
