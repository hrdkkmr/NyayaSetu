/** Voice WebSocket client with ticket auth, keep-alive and automatic reconnection/resume. */

import { api, wsBase } from "@/lib/api";
import type { AiStatus, Lang, TraceEntry } from "@/lib/types";

export type ServerEvent =
  | { type: "ready"; voice_session_id: string; resume_token: string; stt: string; tts: string; language: Lang; resumed: boolean }
  | { type: "state"; value: "listening" | "processing" | "speaking" }
  | { type: "transcript"; text: string; language?: Lang; final: boolean }
  | { type: "assistant_text"; turn_id: string; text: string; cards: unknown[]; phase: string; language: Lang;
      trace?: TraceEntry[]; ai_status?: AiStatus }
  | { type: "tts_sentence"; turn_id: string; index: number; text: string; language: Lang; last: boolean; audio_b64?: string; mime?: string }
  | { type: "turn_end"; turn_id: string }
  | { type: "speech_cancelled" }
  | { type: "error"; code: string; message: string; recoverable: boolean }
  | { type: "pong" }
  | { type: "language"; language: Lang };

export interface SocketOptions {
  caseId: string;
  language: Lang;
  stt: "browser" | "sarvam";
  tts: "browser" | "sarvam";
  onEvent: (e: ServerEvent) => void;
  onStatus: (status: "connecting" | "open" | "reconnecting" | "closed") => void;
}

export class VoiceSocket {
  private ws: WebSocket | null = null;
  private attempts = 0;
  private closedByUser = false;
  private resume: { id: string; token: string } | null = null;
  private ping: ReturnType<typeof setInterval> | null = null;
  private pending: (string | Blob)[] = [];

  constructor(private opts: SocketOptions) {}

  async connect() {
    this.closedByUser = false;
    this.opts.onStatus(this.attempts ? "reconnecting" : "connecting");
    let ticket: string;
    try {
      ticket = (await api<{ ticket: string }>("/voice/ticket", { method: "POST", body: { case_id: this.opts.caseId } })).ticket;
    } catch {
      return this.scheduleReconnect();
    }
    const ws = new WebSocket(`${wsBase()}/api/v1/voice/ws?ticket=${encodeURIComponent(ticket)}`);
    this.ws = ws;
    ws.onopen = () => {
      this.attempts = 0;
      ws.send(JSON.stringify({
        type: "start", language: this.opts.language, stt: this.opts.stt, tts: this.opts.tts,
        voice_session_id: this.resume?.id, resume_token: this.resume?.token,
      }));
      this.ping = setInterval(() => this.sendJson({ type: "ping", t: Date.now() }), 20000);
    };
    ws.onmessage = (msg) => {
      const event = JSON.parse(msg.data) as ServerEvent;
      if (event.type === "ready") {
        this.resume = { id: event.voice_session_id, token: event.resume_token };
        this.opts.onStatus("open");
        const queued = this.pending;
        this.pending = [];
        queued.forEach((p) => ws.send(p));
      }
      this.opts.onEvent(event);
    };
    ws.onclose = (e) => {
      if (this.ping) clearInterval(this.ping);
      this.ws = null;
      if (this.closedByUser || e.code === 4401 || e.code === 4403) {
        this.opts.onStatus("closed");
        return;
      }
      this.scheduleReconnect();
    };
  }

  private scheduleReconnect() {
    if (this.closedByUser) return;
    this.attempts += 1;
    this.opts.onStatus("reconnecting");
    const delay = Math.min(15000, 500 * 2 ** Math.min(this.attempts, 5));
    setTimeout(() => void this.connect(), delay);
  }

  private sendRaw(payload: string | Blob) {
    if (this.ws?.readyState === WebSocket.OPEN && this.resume) this.ws.send(payload);
    else this.pending.push(payload);
  }

  sendJson(payload: Record<string, unknown>) {
    this.sendRaw(JSON.stringify(payload));
  }

  sendAudio(wav: Blob) {
    this.sendRaw(wav);
  }

  close() {
    this.closedByUser = true;
    if (this.ping) clearInterval(this.ping);
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify({ type: "end" }));
    this.ws?.close();
    this.ws = null;
  }
}
