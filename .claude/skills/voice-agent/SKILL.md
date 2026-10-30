---
name: voice-agent
description: Use when working on the voice conversation (WebSocket protocol, Sarvam STT/TTS, browser speech, VAD, barge-in, reconnection, latency).
---

# Voice agent

## Objective
A natural, patient bilingual voice conversation that is only a speech <-> text layer over the same
case workflow — it can never bypass legal reasoning or approvals.

## When to use
`backend/app/api/voice.py`, `integrations/speech.py`, `frontend/src/lib/voice/*`,
`components/conversation/voice-panel.tsx`.

## Design
- Auth: `POST /voice/ticket` → 60 s scoped JWT for one case; WS checks `Origin` against CORS.
- Protocol is documented at the top of `api/voice.py` and in `docs/VOICE_AGENT_DESIGN.md`. Keep the
  frontend `ServerEvent` union in sync.
- STT: `sarvam` (server, 16 kHz WAV utterances cut by client VAD, ≤30 s per Sarvam REST limit) or
  `browser` (Web Speech API; server receives text only). TTS: Sarvam audio per sentence, pipelined
  one sentence ahead, or browser `speechSynthesis`.
- Barge-in: client VAD (raised threshold while speaking) → cancel playback + `interrupt`.
- Reconnect: exponential backoff, `resume_token` restores the voice session; facts live in the DB.
- Every turn calls `api/cases.post_message` — same consent, transcript and audit rules as text.

## Rules
- Sarvam request/response field names must match docs.sarvam.ai (`api-subscription-key`, STT
  multipart `file`/`model`/`language_code`; TTS JSON `text`/`language_code`/`speaker`/`model`;
  response `audios[]`). Re-check the docs before changing models or speakers.
- Store audio only with `consent_store_audio`; always encrypted.
- Keep spoken replies short; `spoken_form` strips URLs and placeholders.

## Security considerations
No API keys in the browser. Tickets are single-case and short-lived. Reject oversized utterances.

## Testing expectations
`tests/test_voice_and_security.py` (ticket, WS turn, fallback to browser when no key, bad ticket,
foreign origin). Manual checks: Hindi, English, code-mixed speech, background noise, long pauses,
interrupting mid-sentence, network drop and resume. Record latency stats from `voice_sessions.stats`.

## Common failure scenarios
- Echo of TTS triggering VAD → raised threshold during `assistantSpeaking`; echoCancellation on.
- Browser recognition is single-language; code-mixed speech is best with Sarvam (`language_code=unknown`).
- `speechSynthesis` has no Hindi voice on some systems — the text is still shown.
