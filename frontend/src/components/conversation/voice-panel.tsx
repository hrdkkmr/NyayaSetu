"use client";

import { useQuery } from "@tanstack/react-query";
import { Loader2, Mic, MicOff, Pause, Play, ShieldCheck, Volume2, VolumeX } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Alert, Badge } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import type { Card, Lang } from "@/lib/types";
import { MicCapture } from "@/lib/voice/mic";
import { VoiceSocket, type ServerEvent } from "@/lib/voice/socket";
import { BrowserRecognizer, browserSttSupported, SpeechOutput } from "@/lib/voice/speech";
import { cn } from "@/lib/utils";

type Status = "off" | "connecting" | "listening" | "processing" | "speaking" | "reconnecting" | "paused";

interface Props {
  caseId: string;
  onUserText: (text: string) => void;
  onAssistant: (text: string, cards: Card[], phase: string, language: Lang) => void;
  registerSender: (send: ((text: string) => void) | null) => void;
}

interface VoiceConfig {
  providers: { browser: { available: boolean }; sarvam: { available: boolean } };
}

export function VoicePanel({ caseId, onUserText, onAssistant, registerSender }: Props) {
  const { t, lang, setLang } = useI18n();
  const { user } = useAuth();
  const { data: config } = useQuery({ queryKey: ["voice-config"], queryFn: () => api<VoiceConfig>("/voice/config") });
  const [status, setStatus] = useState<Status>("off");
  const [interim, setInterim] = useState("");
  const [level, setLevel] = useState(0);
  const [muted, setMuted] = useState(!(user?.preferences.autoplay_voice ?? true));
  const [error, setError] = useState<string | null>(null);
  const [engine, setEngine] = useState<"browser" | "sarvam">("browser");

  const socket = useRef<VoiceSocket | null>(null);
  const mic = useRef<MicCapture | null>(null);
  const recognizer = useRef<BrowserRecognizer | null>(null);
  const output = useRef<SpeechOutput | null>(null);
  const langRef = useRef<Lang>(lang);
  const statusRef = useRef<Status>("off");
  langRef.current = lang;
  statusRef.current = status;

  const wantsServer = user?.preferences.voice_provider === "sarvam" && !!config?.providers.sarvam.available;

  const resumeListening = useCallback(() => {
    if (statusRef.current === "paused" || statusRef.current === "off") return;
    if (mic.current) mic.current.assistantSpeaking = false;
    if (engine === "browser") recognizer.current?.start();
    setStatus("listening");
  }, [engine]);

  const handleEvent = useCallback((e: ServerEvent) => {
    switch (e.type) {
      case "ready":
        setEngine(e.stt === "sarvam" ? "sarvam" : "browser");
        setStatus("listening");
        break;
      case "state":
        if (e.value === "processing") setStatus("processing");
        break;
      case "transcript":
        setInterim("");
        if (e.text) onUserText(e.text);
        break;
      case "assistant_text":
        onAssistant(e.text, e.cards as Card[], e.phase, e.language);
        if (e.language && e.language !== langRef.current) setLang(e.language);
        break;
      case "tts_sentence":
        if (e.audio_b64 && e.mime) output.current?.enqueueAudio(e.audio_b64, e.mime);
        else output.current?.enqueueText(e.text, e.language ?? langRef.current);
        break;
      case "turn_end":
        if (!output.current?.isPlaying) resumeListening();
        break;
      case "error":
        setError(e.message);
        if (e.recoverable) resumeListening();
        break;
      default:
        break;
    }
  }, [onAssistant, onUserText, resumeListening, setLang]);

  const bargeIn = useCallback(() => {
    if (output.current?.isPlaying) {
      output.current.cancel();
      socket.current?.sendJson({ type: "interrupt" });
    }
  }, []);

  const start = async () => {
    setError(null);
    const serverStt = wantsServer;
    if (!serverStt && !browserSttSupported()) {
      setError(t("voice.unsupported"));
      return;
    }
    setStatus("connecting");
    output.current = new SpeechOutput(
      () => resumeListening(),
      () => {
        setStatus("speaking");
        recognizer.current?.stop();
        if (mic.current) mic.current.assistantSpeaking = true;
      },
    );
    output.current.muted = muted;
    output.current.rate = user?.preferences.speech_rate ?? 1;

    try {
      mic.current = new MicCapture({
        onLevel: setLevel,
        onSpeechStart: () => {
          bargeIn();
          if (!serverStt && statusRef.current === "speaking") recognizer.current?.start();
        },
        onUtterance: serverStt ? (wav) => {
          setStatus("processing");
          socket.current?.sendAudio(wav);
        } : undefined,
      });
      await mic.current.start();
    } catch {
      setError(t("voice.noMic"));
      setStatus("off");
      return;
    }

    if (!serverStt) {
      recognizer.current = new BrowserRecognizer(langRef.current, {
        onInterim: (text) => {
          setInterim(text);
          bargeIn();
        },
        onFinal: (text) => {
          setInterim("");
          if (!text) return;
          setStatus("processing");
          recognizer.current?.stop();
          socket.current?.sendJson({ type: "transcript", text, language: langRef.current });
        },
        onError: (code) => {
          if (code === "no_mic") setError(t("voice.noMic"));
        },
      });
      recognizer.current.start();
    }

    socket.current = new VoiceSocket({
      caseId,
      language: langRef.current,
      stt: serverStt ? "sarvam" : "browser",
      tts: wantsServer ? "sarvam" : "browser",
      onEvent: handleEvent,
      onStatus: (s) => {
        if (s === "reconnecting") setStatus("reconnecting");
        if (s === "closed" && statusRef.current !== "off") setStatus("off");
      },
    });
    await socket.current.connect();
    registerSender((text) => socket.current?.sendJson({ type: "text", text }));
  };

  const stop = useCallback(() => {
    registerSender(null);
    output.current?.cancel();
    recognizer.current?.stop();
    mic.current?.stop();
    socket.current?.close();
    socket.current = null;
    mic.current = null;
    recognizer.current = null;
    setStatus("off");
    setLevel(0);
    setInterim("");
  }, [registerSender]);

  useEffect(() => stop, [stop]);

  const togglePause = () => {
    if (status === "paused") {
      mic.current?.pause(false);
      setStatus("listening");
      if (engine === "browser") recognizer.current?.start();
    } else {
      output.current?.cancel();
      mic.current?.pause(true);
      recognizer.current?.stop();
      setStatus("paused");
    }
  };

  const toggleMute = () => {
    const next = !muted;
    setMuted(next);
    if (output.current) {
      output.current.muted = next;
      if (next) output.current.cancel();
    }
  };

  useEffect(() => {
    socket.current?.sendJson({ type: "set_language", language: lang });
    recognizer.current?.setLang(lang);
  }, [lang]);

  const label: Record<Status, string> = {
    off: t("voice.tapToSpeak"), connecting: t("voice.connecting"), listening: t("voice.listening"),
    processing: t("voice.processing"), speaking: t("voice.speaking"), reconnecting: t("voice.reconnecting"), paused: t("voice.idle"),
  };
  const active = status !== "off";

  return (
    <section aria-label={t("chat.switchToVoice")} className="rounded-xl border border-line bg-navy-50 p-4">
      <div className="flex flex-col items-center gap-3">
        <button
          type="button"
          onClick={active ? stop : start}
          className={cn(
            "relative flex size-24 items-center justify-center rounded-full text-white shadow-lg transition-transform focus-visible:outline-offset-4",
            active ? "bg-danger-700" : "bg-navy-800 hover:scale-105",
          )}
          aria-pressed={active}
          aria-label={active ? t("voice.stop") : t("voice.tapToSpeak")}
        >
          {status === "connecting" || status === "processing" ? <Loader2 className="size-10 animate-spin" /> :
            active ? <MicOff className="size-10" /> : <Mic className="size-10" />}
          {status === "listening" && (
            <span className="absolute inset-0 rounded-full ring-4 ring-navy-600/40" style={{ transform: `scale(${1 + level * 0.25})` }} aria-hidden />
          )}
        </button>
        <p className="text-lg font-semibold text-navy-900" aria-live="polite">{label[status]}</p>
        <div className="flex h-8 items-end gap-1" aria-hidden>
          {Array.from({ length: 12 }).map((_, i) => (
            <span
              key={i}
              className="w-1.5 rounded-full bg-navy-700"
              style={{
                height: `${8 + (status === "speaking" ? 18 : level * 24) * Math.abs(Math.sin(i * 1.7 + level * 6))}px`,
                animation: status === "speaking" ? `ns-wave 0.9s ${i * 0.07}s ease-in-out infinite` : undefined,
              }}
            />
          ))}
        </div>
        {interim && <p className="text-center italic text-muted" aria-live="polite">“{interim}”</p>}
        {active && (
          <div className="flex flex-wrap justify-center gap-2">
            <Button size="sm" variant="secondary" onClick={togglePause}>
              {status === "paused" ? <Play aria-hidden /> : <Pause aria-hidden />}
              {status === "paused" ? t("voice.listening") : t("voice.stop")}
            </Button>
            <Button size="sm" variant="secondary" onClick={toggleMute} aria-pressed={muted}>
              {muted ? <VolumeX aria-hidden /> : <Volume2 aria-hidden />}
              {muted ? t("voice.unmute") : t("voice.mute")}
            </Button>
            <Badge tone="info">{t("voice.provider")}: {engine === "sarvam" ? t("voice.providerServer") : t("voice.providerBrowser")}</Badge>
          </div>
        )}
        {status === "speaking" && <p className="text-sm text-muted">{t("voice.pressToInterrupt")}</p>}
        {error && <Alert tone="warning" className="w-full">{error}</Alert>}
        <p className="flex items-start gap-2 text-xs text-muted"><ShieldCheck className="size-4 shrink-0" aria-hidden />{t("voice.privacy")}</p>
      </div>
    </section>
  );
}
