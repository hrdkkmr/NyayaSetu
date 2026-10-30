/**
 * Microphone capture with energy-based voice activity detection (VAD).
 *
 * - Adaptive noise floor (exponential moving average of quiet frames) so it works in
 *   noisy rooms as well as quiet ones.
 * - Speech starts after a few consecutive loud frames; it ends after a configurable
 *   silence. A short pre-roll keeps the first syllable.
 * - While the assistant is speaking, the threshold is raised so the device's own
 *   playback is less likely to be mistaken for the user (barge-in still works).
 * - Each utterance is emitted as 16 kHz mono 16-bit WAV.
 */

export interface MicCallbacks {
  onLevel?: (level: number) => void;
  onSpeechStart?: () => void;
  onUtterance?: (wav: Blob, durationMs: number) => void;
}

export interface VadOptions {
  silenceMs: number;
  minSpeechMs: number;
  maxUtteranceMs: number;
}

const TARGET_RATE = 16000;
const FRAME = 2048;

export class MicCapture {
  private ctx: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private node: ScriptProcessorNode | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private noiseFloor = 0.005;
  private loudFrames = 0;
  private quietMs = 0;
  private speaking = false;
  private chunks: Float32Array[] = [];
  private preroll: Float32Array[] = [];
  private paused = false;
  public assistantSpeaking = false;

  constructor(private cb: MicCallbacks, private opts: VadOptions = { silenceMs: 800, minSpeechMs: 350, maxUtteranceMs: 28000 }) {}

  async start(): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
    });
    const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    this.ctx = new Ctx();
    this.source = this.ctx.createMediaStreamSource(this.stream);
    this.node = this.ctx.createScriptProcessor(FRAME, 1, 1);
    this.node.onaudioprocess = (e) => this.process(e.inputBuffer.getChannelData(0));
    this.source.connect(this.node);
    this.node.connect(this.ctx.destination);
  }

  pause(paused: boolean) {
    this.paused = paused;
    if (paused) this.reset();
  }

  stop() {
    this.node?.disconnect();
    this.source?.disconnect();
    this.stream?.getTracks().forEach((t) => t.stop());
    void this.ctx?.close();
    this.node = null;
    this.source = null;
    this.stream = null;
    this.ctx = null;
    this.reset();
  }

  private reset() {
    this.speaking = false;
    this.loudFrames = 0;
    this.quietMs = 0;
    this.chunks = [];
  }

  private process(input: Float32Array) {
    if (!this.ctx) return;
    const frame = new Float32Array(input);
    let sum = 0;
    for (let i = 0; i < frame.length; i++) sum += frame[i] * frame[i];
    const rms = Math.sqrt(sum / frame.length);
    this.cb.onLevel?.(Math.min(1, rms / Math.max(this.noiseFloor * 8, 0.04)));
    if (this.paused) return;

    const frameMs = (frame.length / this.ctx.sampleRate) * 1000;
    const factor = this.assistantSpeaking ? 6 : 3;
    const threshold = Math.max(this.noiseFloor * factor, this.assistantSpeaking ? 0.04 : 0.012);
    const loud = rms > threshold;
    if (!loud && !this.speaking) this.noiseFloor = this.noiseFloor * 0.95 + rms * 0.05;

    if (!this.speaking) {
      this.preroll.push(frame);
      if (this.preroll.length > 4) this.preroll.shift();
      this.loudFrames = loud ? this.loudFrames + 1 : 0;
      if (this.loudFrames >= (this.assistantSpeaking ? 4 : 2)) {
        this.speaking = true;
        this.quietMs = 0;
        this.chunks = [...this.preroll];
        this.preroll = [];
        this.cb.onSpeechStart?.();
      }
      return;
    }

    this.chunks.push(frame);
    this.quietMs = loud ? 0 : this.quietMs + frameMs;
    const durationMs = (this.chunks.length * frame.length * 1000) / this.ctx.sampleRate;
    if (this.quietMs >= this.opts.silenceMs || durationMs >= this.opts.maxUtteranceMs) {
      const speechMs = durationMs - this.quietMs;
      const chunks = this.chunks;
      const rate = this.ctx.sampleRate;
      this.reset();
      if (speechMs >= this.opts.minSpeechMs) this.cb.onUtterance?.(encodeWav(chunks, rate), durationMs);
    }
  }
}

export function encodeWav(chunks: Float32Array[], inputRate: number): Blob {
  const length = chunks.reduce((n, c) => n + c.length, 0);
  const merged = new Float32Array(length);
  let offset = 0;
  for (const c of chunks) {
    merged.set(c, offset);
    offset += c.length;
  }
  const ratio = inputRate / TARGET_RATE;
  const outLength = Math.floor(merged.length / ratio);
  const pcm = new Int16Array(outLength);
  for (let i = 0; i < outLength; i++) {
    // Simple averaging decimation (acts as a low-pass filter before downsampling).
    const start = Math.floor(i * ratio);
    const end = Math.min(merged.length, Math.floor((i + 1) * ratio));
    let acc = 0;
    for (let j = start; j < end; j++) acc += merged[j];
    const sample = Math.max(-1, Math.min(1, acc / Math.max(1, end - start)));
    pcm[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  const buffer = new ArrayBuffer(44 + pcm.length * 2);
  const view = new DataView(buffer);
  const write = (o: number, s: string) => [...s].forEach((ch, i) => view.setUint8(o + i, ch.charCodeAt(0)));
  write(0, "RIFF");
  view.setUint32(4, 36 + pcm.length * 2, true);
  write(8, "WAVE");
  write(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, TARGET_RATE, true);
  view.setUint32(28, TARGET_RATE * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  write(36, "data");
  view.setUint32(40, pcm.length * 2, true);
  new Int16Array(buffer, 44).set(pcm);
  return new Blob([buffer], { type: "audio/wav" });
}
