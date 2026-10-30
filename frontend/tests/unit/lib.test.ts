import { describe, expect, it } from "vitest";

import en from "@/lib/i18n/en";
import hi from "@/lib/i18n/hi";
import { encodeWav } from "@/lib/voice/mic";
import { formatINR } from "@/lib/utils";

function keys(obj: object, prefix = ""): string[] {
  return Object.entries(obj).flatMap(([k, v]) =>
    typeof v === "object" && v !== null ? keys(v, `${prefix}${k}.`) : [`${prefix}${k}`],
  );
}

describe("i18n dictionaries", () => {
  it("Hindi covers every English key", () => {
    expect(keys(hi).sort()).toEqual(keys(en).sort());
  });
  it("Hindi strings are actually translated (contain Devanagari) for core UI", () => {
    expect(hi.nav.dashboard).toMatch(/[ऀ-ॿ]/);
    expect(hi.voice.tapToSpeak).toMatch(/[ऀ-ॿ]/);
    expect(hi.common.notAdvice).toMatch(/[ऀ-ॿ]/);
  });
  it("keeps placeholders in both languages", () => {
    expect(en.dashboard.daysLeft).toContain("{n}");
    expect(hi.dashboard.daysLeft).toContain("{n}");
  });
});

describe("formatINR", () => {
  it("uses Indian digit grouping", () => {
    expect(formatINR("5499999")).toContain("54,99,999");
    expect(formatINR(null)).toBe("—");
  });
});

describe("encodeWav", () => {
  it("produces a 16 kHz mono 16-bit WAV with the right size", async () => {
    const second = new Float32Array(48000).fill(0.25);
    const blob = encodeWav([second], 48000);
    const buf = new DataView(await blob.arrayBuffer());
    const tag = (o: number) => String.fromCharCode(...[0, 1, 2, 3].map((i) => buf.getUint8(o + i)));
    expect(tag(0)).toBe("RIFF");
    expect(tag(8)).toBe("WAVE");
    expect(buf.getUint32(24, true)).toBe(16000);
    expect(buf.getUint16(22, true)).toBe(1);
    expect(buf.getUint32(40, true)).toBe(16000 * 2);
    expect(buf.getInt16(44, true)).toBeGreaterThan(8000);
  });
});

describe("safeNext (post-login redirect)", () => {
  it("allows same-origin paths and blocks open redirects", async () => {
    const { safeNext } = await import("@/lib/utils");
    expect(safeNext("/cases/abc?tab=filing")).toBe("/cases/abc?tab=filing");
    expect(safeNext("//evil.com")).toBe("/dashboard");
    expect(safeNext(String.raw`/\evil.com`)).toBe("/dashboard");
    expect(safeNext("https://evil.com")).toBe("/dashboard");
    expect(safeNext(null)).toBe("/dashboard");
  });
});
