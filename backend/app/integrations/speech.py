"""Speech provider abstraction.

Server-side providers:
  * Sarvam AI - STT `POST /speech-to-text` (saaras), TTS `POST /text-to-speech` (bulbul).
    Request/response shapes follow docs.sarvam.ai as read on 2026-10-30.

Client-side provider:
  * "browser" - the Web Speech API in the user's browser. The server never receives audio;
    it only receives the recognised text over the same WebSocket. This keeps voice usable
    when no speech credentials are configured.

The voice layer only converts speech <-> text. All legal reasoning happens in the case
workflow; a speech provider can never make or approve a decision.
"""

from __future__ import annotations

import base64
import logging
import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

LANG_CODES = {"hi": "hi-IN", "en": "en-IN"}
MAX_STT_SECONDS = 30  # Sarvam REST limit per request
MAX_TTS_CHARS = 1500  # conservative: bulbul:v2 limit; v3 allows 2500


class SpeechError(RuntimeError):
    pass


@dataclass
class Transcript:
    text: str
    language: str | None
    provider: str
    latency_ms: int


@dataclass
class SynthesizedAudio:
    audio: bytes
    mime_type: str
    provider: str
    latency_ms: int


class STTProvider(Protocol):
    name: str

    async def transcribe(self, audio: bytes, mime_type: str, language: str | None) -> Transcript: ...


class TTSProvider(Protocol):
    name: str

    async def synthesize(self, text: str, language: str, speaker: str | None, pace: float) -> SynthesizedAudio: ...


class SarvamSTT:
    name = "sarvam"

    async def transcribe(self, audio: bytes, mime_type: str, language: str | None) -> Transcript:
        s = get_settings()
        if not s.sarvam_api_key:
            raise SpeechError("Sarvam API key not configured")
        started = time.perf_counter()
        ext = {"audio/wav": "wav", "audio/webm": "webm", "audio/ogg": "ogg", "audio/mpeg": "mp3"}.get(
            mime_type.split(";")[0], "wav")
        data = {"model": s.sarvam_stt_model, "language_code": LANG_CODES.get(language or "", "unknown")}
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{s.sarvam_api_base}/speech-to-text",
                    headers={"api-subscription-key": s.sarvam_api_key},
                    files={"file": (f"utterance.{ext}", audio, mime_type.split(";")[0])},
                    data=data,
                )
        except httpx.HTTPError as exc:
            raise SpeechError(f"Speech service unreachable ({type(exc).__name__})") from exc
        if resp.status_code != 200:
            raise SpeechError(f"Speech recognition failed (HTTP {resp.status_code})")
        body = resp.json()
        code = body.get("language_code") or ""
        return Transcript(
            text=(body.get("transcript") or "").strip(),
            language="hi" if code.startswith("hi") else ("en" if code.startswith("en") else language),
            provider=self.name,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )


class SarvamTTS:
    name = "sarvam"

    async def synthesize(self, text: str, language: str, speaker: str | None, pace: float) -> SynthesizedAudio:
        s = get_settings()
        if not s.sarvam_api_key:
            raise SpeechError("Sarvam API key not configured")
        started = time.perf_counter()
        payload = {
            "text": text[:MAX_TTS_CHARS],
            "language_code": LANG_CODES.get(language, "en-IN"),
            "model": s.sarvam_tts_model,
            "speaker": speaker or (s.sarvam_tts_speaker_hi if language == "hi" else s.sarvam_tts_speaker_en),
            "pace": max(0.5, min(2.0, pace)),
            "speech_sample_rate": 22050,
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(f"{s.sarvam_api_base}/text-to-speech",
                                         headers={"api-subscription-key": s.sarvam_api_key}, json=payload)
        except httpx.HTTPError as exc:
            raise SpeechError(f"Speech service unreachable ({type(exc).__name__})") from exc
        if resp.status_code != 200:
            raise SpeechError(f"Speech synthesis failed (HTTP {resp.status_code})")
        audios = resp.json().get("audios") or []
        if not audios:
            raise SpeechError("Speech synthesis returned no audio")
        return SynthesizedAudio(base64.b64decode(audios[0]), "audio/wav", self.name,
                                int((time.perf_counter() - started) * 1000))


def sarvam_configured() -> bool:
    return bool(get_settings().sarvam_api_key)


def available_providers() -> dict[str, dict[str, object]]:
    return {
        "browser": {"available": True, "where": "client",
                    "note": "Uses the browser's built-in speech recognition and voices (quality varies by browser)."},
        "sarvam": {"available": sarvam_configured(), "where": "server",
                   "stt_model": get_settings().sarvam_stt_model, "tts_model": get_settings().sarvam_tts_model,
                   "note": None if sarvam_configured() else "Set SARVAM_API_KEY to enable."},
    }


def get_stt() -> STTProvider | None:
    return SarvamSTT() if sarvam_configured() else None


def get_tts() -> TTSProvider | None:
    return SarvamTTS() if sarvam_configured() else None
