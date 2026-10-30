# Voice Agent Design

Voice is a speech ⇄ text layer over the same case workflow used for typed messages. It can never
make or approve legal decisions.

## Pipeline
```
Mic → client VAD (energy, adaptive noise floor, pre-roll) ─┬─ stt=sarvam: 16 kHz WAV utterance → WS → Sarvam STT
                                                           └─ stt=browser: Web Speech API → text → WS
WS → post_message() → LangGraph workflow → reply text
reply → sentence split → tts=sarvam: Sarvam TTS per sentence (one-ahead pipelining) → audio frames
                        tts=browser: text frames → speechSynthesis
Barge-in: VAD (raised threshold while speaking) → cancel playback → {"type":"interrupt"}
```

## Providers
| Provider | STT | TTS | Notes |
|---|---|---|---|
| Browser (default, no credentials) | Web Speech API (`hi-IN` / `en-IN`) | `speechSynthesis` | Chrome/Edge; one language per recogniser; voices vary by OS |
| Sarvam AI (`SARVAM_API_KEY`) | `POST /speech-to-text`, `saaras:v4`, `language_code=hi-IN|en-IN|unknown` | `POST /text-to-speech`, `bulbul:v3`, speaker `priya`, base64 WAV in `audios[]` | REST STT limited to 30 s per request (client cuts utterances ≤ 28 s) |

Sarvam field names were taken from docs.sarvam.ai on 2026-10-30. A streaming STT WebSocket
(`/speech-to-text-realtime/ws`) exists and is the planned upgrade for partial transcripts; no
streaming TTS endpoint was found in the docs read.

**Speech-to-speech alternative:** evaluated as an option; not implemented, because a realtime
speech-to-speech model would generate replies outside the grounded workflow. Any future
experiment must route text through `post_message` (see KNOWN_LIMITATIONS).

## WebSocket protocol (`/api/v1/voice/ws?ticket=…`)
Client → server: `start{language, stt, tts, voice_session_id?, resume_token?}`, binary WAV,
`transcript{text, language}`, `text{text}`, `interrupt`, `set_language`, `ping`, `end`.
Server → client: `ready{voice_session_id, resume_token, stt, tts, language, resumed}`,
`state{listening|processing|speaking}`, `transcript`, `assistant_text{text, cards, phase}`,
`tts_sentence{index, text, audio_b64?, mime?, last}`, `turn_end`, `speech_cancelled`,
`error{code, message, recoverable}`, `pong`, `language`.

Security: tickets are 60 s JWTs scoped to one user + case; `Origin` must be in `CORS_ORIGINS`;
utterances over the size limit are rejected; one turn at a time per connection.

## Conversation behaviour
One question per turn; varied, short acknowledgements (no filler); empathy for frustration or
confusion without claiming emotions; explanations of why a question matters (time limit, amount →
forum); retry hints for unparseable answers; skip with "skip" / "पता नहीं"; language follows the
user (Devanagari or Hinglish → Hindi). Spoken text strips URLs and placeholders.

## Recovery
Client reconnects with exponential backoff and `resume_token`; the server restores the voice
session; all facts are in the DB so the conversation continues. Errors are recoverable unless the
case is inaccessible.

## Privacy
Audio is converted to text and discarded unless `consent_store_audio` (then encrypted). Transcripts
follow `consent_store_transcripts`. Session stats (turns, interruptions, average STT / turn /
first-audio latency) are stored in `voice_sessions.stats` for benchmarking.

## Verification status
- Automated: ticket auth, origin check, browser-mode turn, fallback to browser when Sarvam is not
  configured, sentence events (`tests/test_voice_and_security.py`); Hindi turn over a real
  browser WebSocket.
- Not yet verified: live microphone sessions, Sarvam calls (no key available), noise/pause/
  code-switching quality, latency benchmarks. See TESTING_STRATEGY.md for the manual protocol.
