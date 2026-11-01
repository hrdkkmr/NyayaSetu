# Agent Architecture

Implemented with LangGraph (`backend/app/agents/graph.py`). One graph run per trigger; the
durable part of the state is checkpointed to `workflow_instances` (optimistic `revision`), facts
live in `case_facts`, and every node run is recorded in `agent_executions`.

```
START ─┬ message ──────────► safety ─► intake ─► classification ─┬► referral ─► END
       │                                                         ├► ask (next question) ─► END
       │                                                         └► research ─► planning ─► END
       ├ refresh_analysis ─► research ─► planning ─► END
       ├ generate_documents ► documents (verification per version) ─► END
       ├ approval_decided ──► filing ─► END          (human-approval interrupt resumes here)
       └ filing_update ─────► tracking ─► END
```

## Agents and their tool access
| Agent (node) | Responsibility | May write | Never |
|---|---|---|---|
| Safety | Detect danger / self-harm language; reply with 112 / Tele-MANAS | — | continue legal flow that turn |
| Intake | Extract candidate facts from the message (LLM structured output if consented, else rules); confirmations, skips, retries | `case_facts` (with provenance), case summary columns | promote inferences silently |
| Classification | Route: consumer vs criminal / cyber / family / employment / property / other / unclear | `cases.category`, review flag | force a non-consumer matter into the consumer flow |
| Ask (intake question) | One question at a time; batch confirmation of inferences; format hints; answers user questions from grounded rules or retrieval | asked slot | answer from low-confidence retrieval |
| Legal research | Hybrid retrieval per topic; deterministic rule outcomes grounded in ingested provisions; plain-language explanations | `legal_citations`, `cases.analysis` | state law not in the knowledge base |
| Workflow planning | Ordered steps, optional vs required, limitation deadline (estimate) | `workflow_steps`, `deadlines` | claim optional steps are mandatory |
| Document generation | Deterministic templates from confirmed facts only | `generated_documents`, `document_versions` | invent clauses/format |
| Verification | Placeholders, conflicts, unconfirmed inferences, date order, amounts, limitation, consumer status, ungrounded rules | `document_versions.validation` | approve anything |
| Filing | Readiness after approvals; guided e-Jagriti filing | case status | submit, sign, pay |
| Case tracking | Record user-reported filing, update plan | `workflow_steps` | mark official status |

Approvals, authorisations, acknowledgements and verification are API actions by the user (or a
reviewer) — never by an agent.

## State (`agents/state.py`)
Durable keys: phase, asked_slot, skipped_slots, slot_attempts, batch_pending, batch_declined,
turns, category, category_confidence, routing, rule_outcomes, research_topics, citations, plan,
documents, verification, approval, safety, language. Facts are rebuilt from the DB each run.

## Provenance policy
- Direct answers to the asked question and the user's own description → `user_stated`.
- Values the system derives from narrative (e.g. "Amazon" ⇒ online purchase) → `ai_inference`,
  confirmed in a batch ("Here's what I noted … Is all of that correct?") or individually.
- Uploaded-document values become `document_extracted` only when the user accepts them.
- Different sources coexist; conflicts are surfaced by verification and block approval.

## LLM usage (`agents/llm.py`)
Provider abstraction: `AnthropicProvider` (Claude `claude-opus-5-5`, structured outputs via
`beta.messages.parse`, server-side refusal fallbacks), `OpenAICompatibleProvider`
(`LLM_PROVIDER=openai_compatible`: any OpenAI-style Chat Completions API such as xAI Grok or Groq,
over httpx; `response_format` JSON schema, falling back to JSON mode after a 400; replies validated
against the Pydantic model) or `OfflineProvider`. Used only when the
user has `consent_external_ai` and a key is configured. Safeguards: excerpt must appear in the
user's text or the fact becomes an inference; rephrasings rejected if they cite unretrieved
provisions or make guarantees; any LLM error falls back to rules.

## Recovery
Each node runs in a savepoint with one retry; failures produce an `agent_executions` error row
and a polite bilingual message, and the workflow remains resumable. Unparseable answers get a
format hint; after three attempts the slot is skipped and stays visibly missing.

## Tests
`backend/tests/test_workflow.py` covers incomplete info, inferences, Hindi, referral, commercial
exclusion, safety, persistence/resume, failed tools, consent gating, excerpt validation, LLM
failure fallback and unsafe rephrase rejection.
