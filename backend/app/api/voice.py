"""Voice conversation over WebSocket.

Protocol (JSON text frames unless noted) - see docs/VOICE_AGENT_DESIGN.md:

client → server
  {"type":"start","language":"hi|en","stt":"browser|sarvam","tts":"browser|sarvam","resume_token":?}
  <binary frame>   one complete utterance (16 kHz mono WAV) cut by client-side VAD   [stt=sarvam]
  {"type":"transcript","text":"...","language":"hi|en"}                              [stt=browser]
  {"type":"text","text":"..."}            typed fallback inside the voice session
  {"type":"interrupt"}                    barge-in: stop speaking now
  {"type":"set_language","language":"hi|en"}
  {"type":"ping"} / {"type":"end"}

server → client
  ready, state(listening|processing|speaking), transcript, assistant_text, tts_sentence, turn_end,
  error(code, message, recoverable), pong

The voice layer only moves speech <-> text. Every utterance goes through the same case
workflow as typed messages, so voice can never bypass legal reasoning or approvals.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import re
import time
import uuid
from datetime import UTC
from typing import Any

import jwt
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.cases import post_message
from app.config import get_settings
from app.core.deps import RequestContext, get_context, get_owned_case
from app.core.errors import RateLimitedError
from app.core.ratelimit import limiter
from app.core.security import create_scoped_token, decode_token, keyed_hash, new_opaque_token
from app.db.base import utcnow
from app.db.session import get_db, session_scope
from app.integrations.speech import (
    MAX_STT_SECONDS,
    SpeechError,
    available_providers,
    get_stt,
    get_tts,
)
from app.models import AuthSession, Case, User, VoiceSession
from app.services.storage import store_encrypted

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/voice", tags=["voice"])

MAX_UTTERANCE_BYTES = 16000 * 2 * MAX_STT_SECONDS + 1024  # 16 kHz, 16-bit mono WAV
IDLE_TIMEOUT_SECONDS = 300
MAX_SESSION_SECONDS = 2 * 60 * 60

# Single-use tickets. In-process set is sufficient for one API instance; with several instances
# the 60 s ticket lifetime bounds replay. (Move to Redis SETNX when scaling out.)
_used_tickets: dict[str, int] = {}


def _consume_ticket(jti: str, exp: int) -> bool:
    now = int(time.time())
    for key in [k for k, e in _used_tickets.items() if e < now]:
        _used_tickets.pop(key, None)
    if jti in _used_tickets:
        return False
    _used_tickets[jti] = exp
    return True


async def session_active(db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    session = await db.get(AuthSession, session_id)
    if session is None or session.user_id != user_id or session.revoked_at is not None:
        return False
    expires = session.expires_at if session.expires_at.tzinfo else session.expires_at.replace(tzinfo=UTC)
    user = await db.get(User, user_id)
    return expires > utcnow() and user is not None and user.is_active
_SENTENCE = re.compile(r"(?<=[.!?।])\s+")


class TicketIn(BaseModel):
    case_id: uuid.UUID


@router.get("/config")
async def voice_config(_: RequestContext = Depends(get_context)) -> dict[str, Any]:
    return {"providers": available_providers(), "max_utterance_seconds": MAX_STT_SECONDS,
            "languages": [{"code": "hi", "bcp47": "hi-IN"}, {"code": "en", "bcp47": "en-IN"}]}


@router.post("/ticket")
async def voice_ticket(payload: TicketIn, ctx: RequestContext = Depends(get_context),
                       db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Short-lived, single-case ticket for opening the voice WebSocket."""
    case = await get_owned_case(db, payload.case_id, ctx.user)
    token = create_scoped_token(str(ctx.user.id), "voice", 60, case=str(case.id), sid=str(ctx.session_id))
    return {"ticket": token, "expires_in": 60}


def split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENTENCE.split(text) if p.strip()]
    merged: list[str] = []
    for part in parts:  # avoid tiny fragments that sound choppy
        if merged and len(merged[-1]) < 25:
            merged[-1] = f"{merged[-1]} {part}"
        else:
            merged.append(part)
    return merged or ([text] if text else [])


def spoken_form(text: str) -> str:
    """Make text friendlier to speak: drop URLs and bracketed artefacts."""
    text = re.sub(r"https?://\S+", "", text)
    text = text.replace("[●]", "").replace("“", "").replace("”", "")
    return re.sub(r"\s{2,}", " ", text).strip()


class VoiceConnection:
    def __init__(self, ws: WebSocket, user_id: uuid.UUID, case_id: uuid.UUID, session_id: uuid.UUID) -> None:
        self.ws = ws
        self.user_id = user_id
        self.case_id = case_id
        self.auth_session_id = session_id
        self.language = "en"
        self.stt_mode = "browser"
        self.tts_mode = "browser"
        self.voice_session_id: uuid.UUID | None = None
        self.speaking_task: asyncio.Task[None] | None = None
        self.turn_lock = asyncio.Lock()
        self.stats: dict[str, Any] = {"turns": 0, "interruptions": 0, "stt_ms": [], "turn_ms": [], "tts_first_ms": []}
        self.store_audio = False

    async def send(self, payload: dict[str, Any]) -> None:
        with contextlib.suppress(RuntimeError, WebSocketDisconnect):
            await self.ws.send_json(payload)

    async def state(self, value: str) -> None:
        await self.send({"type": "state", "value": value})

    async def error(self, code: str, message: str, recoverable: bool = True) -> None:
        await self.send({"type": "error", "code": code, "message": message, "recoverable": recoverable})

    async def start(self, msg: dict[str, Any]) -> None:
        self.language = str(msg["language"]) if msg.get("language") in ("hi", "en") else "en"
        providers = available_providers()
        self.stt_mode = "sarvam" if msg.get("stt") == "sarvam" and providers["sarvam"]["available"] else "browser"
        self.tts_mode = "sarvam" if msg.get("tts") == "sarvam" and providers["sarvam"]["available"] else "browser"
        resume = msg.get("resume_token")
        async with session_scope() as db:
            user = await db.get(User, self.user_id)
            await db.refresh(user, attribute_names=["preferences"])
            self.store_audio = bool(user and user.preferences and user.preferences.consent_store_audio)
            vs: VoiceSession | None = None
            if resume and msg.get("voice_session_id"):
                candidate = await db.get(VoiceSession, uuid.UUID(str(msg["voice_session_id"])))
                if candidate and candidate.user_id == self.user_id and candidate.resume_token_hash == keyed_hash(resume, "voice"):
                    vs = candidate
                    vs.status = "active"
                    self.stats = {**self.stats, **(vs.stats or {})}
            token = new_opaque_token()
            if vs is None:
                vs = VoiceSession(user_id=self.user_id, stt_provider=self.stt_mode, tts_provider=self.tts_mode,
                                  status="active", stats={}, audio_stored=self.store_audio)
                db.add(vs)
            vs.resume_token_hash = keyed_hash(token, "voice")
            await db.flush()
            self.voice_session_id = vs.id
        await self.send({"type": "ready", "voice_session_id": str(self.voice_session_id), "resume_token": token,
                         "stt": self.stt_mode, "tts": self.tts_mode, "language": self.language,
                         "resumed": bool(resume and self.stats["turns"])})
        await self.state("listening")

    async def interrupt(self) -> None:
        if self.speaking_task and not self.speaking_task.done():
            self.speaking_task.cancel()
            self.stats["interruptions"] += 1
            await self.send({"type": "speech_cancelled"})
        await self.state("listening")

    async def handle_audio(self, data: bytes) -> None:
        if self.stt_mode != "sarvam":
            await self.error("stt_not_server", "Audio was sent but server speech recognition is not active.")
            return
        if len(data) > MAX_UTTERANCE_BYTES:
            await self.error("utterance_too_long", "That was a long stretch of speech. Please pause a little more often.")
            return
        await self.interrupt()
        stt = get_stt()
        if stt is None:
            await self.error("stt_unavailable", "Speech recognition is unavailable. Please type instead.")
            return
        await self.state("processing")
        try:
            transcript = await stt.transcribe(data, "audio/wav", self.language)
        except SpeechError as exc:
            logger.warning("STT failed: %s", exc)
            await self.error("stt_failed", "I couldn't hear that clearly. Please try again or type your answer.")
            await self.state("listening")
            return
        self.stats["stt_ms"].append(transcript.latency_ms)
        if self.store_audio:
            key = await store_encrypted(f"voice/{self.user_id}", data)
            # Keys are recorded so recordings can be exported/deleted with the account or on consent withdrawal.
            async with session_scope() as db:
                vs = await db.get(VoiceSession, self.voice_session_id)
                if vs is not None:
                    vs.stats = {**(vs.stats or {}), "audio_keys": [*(vs.stats or {}).get("audio_keys", []), key]}
        if not transcript.text:
            await self.send({"type": "transcript", "text": "", "final": True})
            await self.state("listening")
            return
        if transcript.language in ("hi", "en"):
            self.language = transcript.language
        await self.send({"type": "transcript", "text": transcript.text, "language": self.language, "final": True})
        await self.run_turn(transcript.text, modality="voice")

    async def run_turn(self, text: str, modality: str) -> None:
        text = text.strip()[:4000]
        if not text:
            return
        async with self.turn_lock:
            started = time.perf_counter()
            await self.state("processing")
            try:
                async with session_scope() as db:
                    user = await db.get(User, self.user_id)
                    case = await db.get(Case, self.case_id)
                    if not await session_active(db, self.auth_session_id, self.user_id):
                        await self.error("session_ended", "Your session has ended. Please sign in again.", recoverable=False)
                        await self.ws.close(code=4401)
                        return
                    await limiter.hit(f"user:{self.user_id}", get_settings().rate_limit_per_minute)
                    if user is None or not user.is_active or case is None or case.user_id != user.id:
                        await self.error("forbidden", "This case is not available.", recoverable=False)
                        return
                    ctx = RequestContext(user=user, session_id=self.auth_session_id, ip_hash=None,
                                         user_agent="voice", via_cookie=False)
                    result = await post_message(db, case, ctx, text, modality, self.language)
            except RateLimitedError:
                await self.error("rate_limited", "Please slow down a little and try again in a minute.")
                await self.state("listening")
                return
            except Exception:  # noqa: BLE001
                logger.exception("Voice turn failed")
                await self.error("turn_failed", "Something went wrong. Your earlier answers are saved — please repeat that.")
                await self.state("listening")
                return
            self.stats["turns"] += 1
            self.stats["turn_ms"].append(int((time.perf_counter() - started) * 1000))
            reply = result["assistant_message"]["content"]
            self.language = result.get("language") or self.language
            turn_id = str(uuid.uuid4())
            await self.send({"type": "assistant_text", "turn_id": turn_id, "text": reply,
                             "cards": result["assistant_message"].get("cards", []), "phase": result.get("phase"),
                             "language": self.language, "case": result.get("case"),
                             "trace": result.get("trace", []), "ai_status": result.get("ai_status", {})})
            self.speaking_task = asyncio.create_task(self.speak(turn_id, reply, started))

    async def speak(self, turn_id: str, text: str, started: float) -> None:
        await self.state("speaking")
        sentences = split_sentences(spoken_form(text))
        tts = get_tts() if self.tts_mode == "sarvam" else None
        pending: asyncio.Task[Any] | None = None
        try:
            # Synthesise the next sentence while the current one plays (one-ahead pipelining).
            if tts and sentences:
                pending = asyncio.create_task(tts.synthesize(sentences[0], self.language, None, 1.0))
            for index, sentence in enumerate(sentences):
                payload: dict[str, Any] = {"type": "tts_sentence", "turn_id": turn_id, "index": index,
                                           "text": sentence, "language": self.language,
                                           "last": index == len(sentences) - 1}
                if tts and pending:
                    try:
                        audio = await pending
                        payload["audio_b64"] = base64.b64encode(audio.audio).decode()
                        payload["mime"] = audio.mime_type
                    except SpeechError:
                        payload["tts_fallback"] = "browser"
                    if index == 0:
                        self.stats["tts_first_ms"].append(int((time.perf_counter() - started) * 1000))
                    pending = (asyncio.create_task(tts.synthesize(sentences[index + 1], self.language, None, 1.0))
                               if index + 1 < len(sentences) else None)
                await self.send(payload)
            await self.send({"type": "turn_end", "turn_id": turn_id})
        except asyncio.CancelledError:
            if pending:
                pending.cancel()
            raise
        finally:
            await self.state("listening")

    async def close(self) -> None:
        if self.speaking_task and not self.speaking_task.done():
            self.speaking_task.cancel()
        if self.voice_session_id:
            async with session_scope() as db:
                vs = await db.get(VoiceSession, self.voice_session_id)
                if vs:
                    vs.status = "disconnected"
                    vs.ended_at = utcnow()

                    def avg(values: list[int]) -> int | None:
                        return int(sum(values) / len(values)) if values else None

                    vs.stats = {"turns": self.stats["turns"], "interruptions": self.stats["interruptions"],
                                "avg_stt_ms": avg(self.stats["stt_ms"]), "avg_turn_ms": avg(self.stats["turn_ms"]),
                                "avg_tts_first_ms": avg(self.stats["tts_first_ms"])}


@router.websocket("/ws")
async def voice_ws(ws: WebSocket, ticket: str) -> None:
    origin = ws.headers.get("origin")
    if origin and origin not in get_settings().cors_origins:
        await ws.close(code=4403)
        return
    try:
        claims = decode_token(ticket, "voice")
        user_id, case_id, session_id = uuid.UUID(claims["sub"]), uuid.UUID(claims["case"]), uuid.UUID(claims["sid"])
        if not _consume_ticket(str(claims["jti"]), int(claims["exp"])):
            raise ValueError("ticket already used")
    except (jwt.PyJWTError, KeyError, ValueError):
        await ws.close(code=4401)
        return
    async with session_scope() as db:
        if not await session_active(db, session_id, user_id):
            await ws.close(code=4401)
            return
    await ws.accept()
    started_at = time.monotonic()
    conn = VoiceConnection(ws, user_id, case_id, session_id)
    try:
        while True:
            if time.monotonic() - started_at > MAX_SESSION_SECONDS:
                await conn.error("session_too_long", "This voice session has ended. Start a new one to continue.",
                                 recoverable=False)
                break
            try:
                message = await asyncio.wait_for(ws.receive(), timeout=IDLE_TIMEOUT_SECONDS)
            except TimeoutError:
                await conn.error("idle_timeout", "The voice session was closed after a period of inactivity.",
                                 recoverable=False)
                break
            if message.get("type") == "websocket.disconnect":
                break
            if message.get("bytes") is not None:
                await conn.handle_audio(message["bytes"])
                continue
            try:
                msg = json.loads(message.get("text") or "{}")
            except ValueError:
                await conn.error("bad_message", "Malformed message.")
                continue
            kind = msg.get("type")
            if kind == "start":
                await conn.start(msg)
            elif kind == "transcript":
                await conn.interrupt()
                await conn.send({"type": "transcript", "text": msg.get("text", ""), "final": True})
                if msg.get("language") in ("hi", "en"):
                    conn.language = msg["language"]
                await conn.run_turn(str(msg.get("text", "")), modality="voice")
            elif kind == "text":
                await conn.interrupt()
                await conn.run_turn(str(msg.get("text", "")), modality="text")
            elif kind == "interrupt":
                await conn.interrupt()
            elif kind == "set_language" and msg.get("language") in ("hi", "en"):
                conn.language = msg["language"]
                await conn.send({"type": "language", "language": conn.language})
            elif kind == "ping":
                await conn.send({"type": "pong", "t": msg.get("t")})
            elif kind == "end":
                break
    except WebSocketDisconnect:
        pass
    finally:
        await conn.close()
        with contextlib.suppress(RuntimeError):
            await ws.close()
