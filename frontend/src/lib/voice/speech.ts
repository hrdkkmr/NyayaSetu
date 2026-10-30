/** Browser speech recognition (Web Speech API) and speech output (browser voices or server audio). */

import type { Lang } from "@/lib/types";

const BCP47: Record<Lang, string> = { en: "en-IN", hi: "hi-IN" };

// Minimal typing for the Web Speech API, which TypeScript's DOM lib does not include.
interface RecognitionResult { isFinal: boolean; 0: { transcript: string } }
interface RecognitionEvent { resultIndex: number; results: ArrayLike<RecognitionResult> }
interface Recognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((e: RecognitionEvent) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  onspeechstart: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}

function recognitionCtor(): (new () => Recognition) | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export function browserSttSupported(): boolean {
  return recognitionCtor() !== null;
}

export function browserTtsSupported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

export class BrowserRecognizer {
  private rec: Recognition | null = null;
  private active = false;

  constructor(
    private lang: Lang,
    private handlers: {
      onInterim?: (text: string) => void;
      onFinal: (text: string) => void;
      onSpeechStart?: () => void;
      onError?: (code: string) => void;
    },
  ) {}

  setLang(lang: Lang) {
    this.lang = lang;
    if (this.active) {
      this.stop();
      this.start();
    }
  }

  start() {
    const Ctor = recognitionCtor();
    if (!Ctor) {
      this.handlers.onError?.("unsupported");
      return;
    }
    this.active = true;
    const rec = new Ctor();
    rec.lang = BCP47[this.lang];
    rec.continuous = false;
    rec.interimResults = true;
    rec.onspeechstart = () => this.handlers.onSpeechStart?.();
    rec.onresult = (e) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) this.handlers.onFinal(r[0].transcript.trim());
        else interim += r[0].transcript;
      }
      if (interim) this.handlers.onInterim?.(interim);
    };
    rec.onerror = (e) => {
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        this.active = false;
        this.handlers.onError?.("no_mic");
      } else if (e.error !== "no-speech" && e.error !== "aborted") {
        this.handlers.onError?.(e.error);
      }
    };
    // Recognition stops after each phrase; restart while the session is active.
    rec.onend = () => {
      if (this.active) {
        try {
          rec.start();
        } catch {
          /* already started */
        }
      }
    };
    this.rec = rec;
    try {
      rec.start();
    } catch {
      /* start called twice */
    }
  }

  stop() {
    this.active = false;
    this.rec?.abort();
    this.rec = null;
  }
}

/** Plays sentences in order; `cancel()` stops immediately (barge-in). */
export class SpeechOutput {
  private audio: HTMLAudioElement | null = null;
  private queue: (() => Promise<void>)[] = [];
  private playing = false;
  private generation = 0;
  public muted = false;
  public rate = 1;

  constructor(private onIdle: () => void, private onStart: () => void) {}

  enqueueText(text: string, lang: Lang) {
    if (this.muted || !browserTtsSupported()) return;
    const gen = this.generation;
    this.queue.push(
      () =>
        new Promise<void>((resolve) => {
          if (gen !== this.generation) return resolve();
          const u = new SpeechSynthesisUtterance(text);
          u.lang = BCP47[lang];
          u.rate = this.rate;
          const voice = window.speechSynthesis.getVoices().find((v) => v.lang === BCP47[lang]) ??
            window.speechSynthesis.getVoices().find((v) => v.lang.startsWith(lang));
          if (voice) u.voice = voice;
          u.onend = () => resolve();
          u.onerror = () => resolve();
          window.speechSynthesis.speak(u);
        }),
    );
    void this.drain();
  }

  enqueueAudio(base64: string, mime: string) {
    if (this.muted) return;
    const gen = this.generation;
    this.queue.push(
      () =>
        new Promise<void>((resolve) => {
          if (gen !== this.generation) return resolve();
          const audio = new Audio(`data:${mime};base64,${base64}`);
          audio.playbackRate = this.rate;
          this.audio = audio;
          audio.onended = () => resolve();
          audio.onerror = () => resolve();
          audio.play().catch(() => resolve());
        }),
    );
    void this.drain();
  }

  private async drain() {
    if (this.playing) return;
    this.playing = true;
    this.onStart();
    while (this.queue.length) {
      const next = this.queue.shift()!;
      await next();
    }
    this.playing = false;
    this.audio = null;
    this.onIdle();
  }

  cancel() {
    this.generation += 1;
    this.queue = [];
    if (browserTtsSupported()) window.speechSynthesis.cancel();
    if (this.audio) {
      this.audio.pause();
      this.audio = null;
    }
  }

  get isPlaying() {
    return this.playing;
  }
}
