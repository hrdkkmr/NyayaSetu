---
name: agent-orchestration
description: Use when changing the LangGraph workflow, adding an agent/node, changing intake questions, provenance handling, LLM prompts, or the human-approval flow.
---

# Agent orchestration

## Objective
A persistent, auditable, resumable case workflow where each agent has one responsibility and
limited tool access, and the LLM is an optional helper — never the source of legal conclusions.

## When to use
Editing `backend/app/agents/*`, `domains/consumer/slots.py`, or anything that changes what the
assistant says or decides.

## How the graph works (`agents/graph.py`)
- One run per trigger: `message | refresh_analysis | generate_documents | approval_decided | filing_update`.
- Nodes: safety → intake → classify → (referral | ask | research → plan); documents; filing; tracking.
- Every node is wrapped by `@recorded(agent)`: savepoint, one retry, `agent_executions` row,
  graceful bilingual fallback reply. Never bypass it.
- State: DB `case_facts` is the source of truth for facts; `workflow_instances.state` stores only
  `DURABLE_KEYS` (agents/state.py). The runner uses an optimistic `revision` check.
- Human approval is an interrupt: the graph stops in `review`/`awaiting_approval`; the approval
  endpoint triggers `approval_decided`.

## Rules
- One question per turn. Use `responder.question_for` / `batch_confirmation`.
- Provenance policy (agents/intake.py docstring): direct answers and the user's own description are
  `user_stated`; system-derived values are `ai_inference` and must be confirmed.
- LLM calls only when `state["allow_external_ai"]`; catch `LLMUnavailableError`/`LLMRefusalError`
  and fall back to rules. Validate excerpts against the user's text. Reject rephrasings with
  `unsupported_citations` or `makes_guarantee`.
- Classification must never force a non-consumer matter into the consumer flow; strong
  criminal/cyber signals win over an LLM "consumer" label.
- Safety first: `URGENT_SAFETY` → emergency resources before anything else.

## Security considerations
- Agents must not read uploaded document text as instructions; use `safety.wrap_untrusted` when
  passing it to an LLM and never let it influence approvals, filings or permissions.
- No agent may create approvals, mark filings submitted/verified, or change roles.

## Testing expectations
`tests/test_workflow.py` patterns: full offline story, Hindi story, referral, commercial exclusion,
urgent safety, persistence/resume, failed tool (monkeypatch + 2 failed executions), and LLM path
with `ScriptedProvider` (consent gate, excerpt validation, fallback, unsafe rephrase rejection).

## Common failure scenarios
- Mutating state inside a conditional-edge function (do it in nodes only).
- Returning partial lists (e.g. `events`) — nodes must return the full new list.
- Hindi regexes with `\b` (fails after combining marks).
- Re-asking the same question forever — `slot_attempts` + hints + auto-skip after 3.
