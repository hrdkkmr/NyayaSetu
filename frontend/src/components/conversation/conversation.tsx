"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Keyboard, Mic, Send, User } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { AgentTelemetry, AiStatusBadge } from "@/components/conversation/agent-telemetry";
import { MessageCards } from "@/components/conversation/cards";
import { VoicePanel } from "@/components/conversation/voice-panel";
import { Button } from "@/components/ui/button";
import { Alert, Textarea } from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { AiStatus, Card, ChatMessage, Lang, TraceEntry, TurnResult } from "@/lib/types";
import { cn } from "@/lib/utils";

interface Props {
  caseId: string;
  initialMode?: "text" | "voice";
  initialTurn?: TurnResult | null;
}

function localMessage(role: "user" | "assistant", content: string, extra: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: `local-${Math.random().toString(36).slice(2)}`, role, content, language: null, modality: "voice",
    redacted: false, cards: [], created_at: new Date().toISOString(), ...extra,
  };
}

export function Conversation({ caseId, initialMode = "text", initialTurn = null }: Props) {
  const { t, lang } = useI18n();
  const qc = useQueryClient();
  const [mode, setMode] = useState<"text" | "voice">(initialMode);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [lastTrace, setLastTrace] = useState<TraceEntry[]>(initialTurn?.trace ?? []);
  const [aiStatus, setAiStatus] = useState<AiStatus | null>(initialTurn?.ai_status ?? null);
  const voiceSender = useRef<((text: string) => void) | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["messages", caseId],
    queryFn: () => api<{ messages: ChatMessage[]; store_transcript: boolean | null }>(`/cases/${caseId}/messages`),
  });

  useEffect(() => {
    if (!data) return;
    const stored = data.messages.filter((m) => !m.redacted);
    if (stored.length) setMessages(stored);
    else if (initialTurn) setMessages([initialTurn.user_message, initialTurn.assistant_message]);
  }, [data, initialTurn]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length]);

  const refreshCase = useCallback(() => {
    void qc.invalidateQueries({ queryKey: ["case", caseId] });
    void qc.invalidateQueries({ queryKey: ["agent-trace", caseId] });
  }, [qc, caseId]);

  const recordTelemetry = useCallback((trace?: TraceEntry[], status?: AiStatus) => {
    if (trace) setLastTrace(trace);
    if (status) setAiStatus(status);
  }, []);

  const sendText = async (text: string) => {
    const value = text.trim();
    if (!value || sending) return;
    if (mode === "voice" && voiceSender.current) {
      setMessages((m) => [...m, localMessage("user", value, { modality: "text" })]);
      voiceSender.current(value);
      return;
    }
    setSending(true);
    setMessages((m) => [...m, localMessage("user", value, { modality: "text" })]);
    try {
      const turn = await api<TurnResult>(`/cases/${caseId}/messages`, { method: "POST", body: { text: value, language: lang } });
      setMessages((m) => [...m.slice(0, -1), { ...turn.user_message }, turn.assistant_message]);
      recordTelemetry(turn.trace, turn.ai_status);
      refreshCase();
    } catch (e) {
      setMessages((m) => m.slice(0, -1));
      setDraft(value);
      toast.error(e instanceof ApiError ? e.message : t("common.errorGeneric"));
    } finally {
      setSending(false);
    }
  };

  const onUserVoice = useCallback((text: string) => setMessages((m) => [...m, localMessage("user", text)]), []);
  const onAssistantVoice = useCallback((text: string, cards: Card[], _phase: string, language: Lang,
                                         meta?: { trace?: TraceEntry[]; ai_status?: AiStatus }) => {
    setMessages((m) => [...m, localMessage("assistant", text, { cards, language })]);
    recordTelemetry(meta?.trace, meta?.ai_status);
    refreshCase();
  }, [refreshCase, recordTelemetry]);
  const registerSender = useCallback((send: ((text: string) => void) | null) => {
    voiceSender.current = send;
  }, []);

  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div role="group" className="flex gap-2">
          <Button size="sm" variant={mode === "voice" ? "primary" : "secondary"} onClick={() => setMode("voice")} aria-pressed={mode === "voice"}>
            <Mic aria-hidden /> {t("chat.switchToVoice")}
          </Button>
          <Button size="sm" variant={mode === "text" ? "primary" : "secondary"} onClick={() => setMode("text")} aria-pressed={mode === "text"}>
            <Keyboard aria-hidden /> {t("chat.switchToText")}
          </Button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <AiStatusBadge status={aiStatus} />
          <span className="text-xs text-muted">{t("chat.aiLabel")}</span>
        </div>
      </div>

      {data?.store_transcript === false && <Alert tone="info">{t("chat.notStored")}</Alert>}

      {mode === "voice" && (
        <VoicePanel caseId={caseId} onUserText={onUserVoice} onAssistant={onAssistantVoice} registerSender={registerSender} />
      )}

      <div className="max-h-[60vh] min-h-48 space-y-4 overflow-y-auto rounded-xl border border-line bg-white p-4" aria-live="polite" aria-busy={sending}>
        {isLoading && <p className="text-muted">{t("common.loading")}</p>}
        {messages.map((m) => (
          <div key={m.id} className={cn("flex gap-3", m.role === "user" && "flex-row-reverse")}>
            <span className={cn("flex size-8 shrink-0 items-center justify-center rounded-full",
              m.role === "user" ? "bg-navy-100 text-navy-800" : "bg-navy-800 text-white")} aria-hidden>
              {m.role === "user" ? <User className="size-4" /> : <Bot className="size-4" />}
            </span>
            <div className={cn("max-w-[85%] space-y-1", m.role === "user" && "text-right")}>
              <p className="sr-only">{m.role === "user" ? t("chat.you") : t("chat.assistant")}:</p>
              <div className={cn("inline-block whitespace-pre-wrap rounded-2xl px-4 py-2 text-left",
                m.role === "user" ? "rounded-tr-sm bg-navy-100 text-navy-900" : "rounded-tl-sm border border-line bg-canvas")}>
                {m.modality === "voice" && <Mic className="mr-1 inline size-3.5 text-muted" aria-label="voice" />}
                {m.content}
              </div>
              {m.role === "assistant" && m.cards?.length > 0 && (
                <MessageCards cards={m.cards} caseId={caseId} onReply={sendText} interactive={m.id === lastAssistant?.id} />
              )}
            </div>
          </div>
        ))}
        {sending && <p className="text-sm italic text-muted">{t("chat.thinking")}</p>}
        <div ref={endRef} />
      </div>

      <AgentTelemetry caseId={caseId} lastTrace={lastTrace} />

      <form
        onSubmit={(e) => {
          e.preventDefault();
          const value = draft;
          setDraft("");
          void sendText(value);
        }}
        className="flex items-end gap-2"
      >
        <label htmlFor="chat-input" className="sr-only">{t("chat.placeholder")}</label>
        <Textarea
          id="chat-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              e.currentTarget.form?.requestSubmit();
            }
          }}
          placeholder={t("chat.placeholder")}
          className="min-h-12 flex-1 resize-none"
          rows={1}
          maxLength={4000}
        />
        <Button type="submit" loading={sending} disabled={!draft.trim()} aria-label={t("chat.send")}>
          <Send aria-hidden /> <span className="hidden sm:inline">{t("chat.send")}</span>
        </Button>
      </form>
    </div>
  );
}
