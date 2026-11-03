import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AgentTelemetry, AiStatusBadge, statusKey } from "@/components/conversation/agent-telemetry";
import { I18nProvider } from "@/lib/i18n";
import type { TraceEntry } from "@/lib/types";

const TRACE: TraceEntry[] = [
  { stage: "safety_guard", agent: "safety", status: "succeeded", provider: "rules", model: null, attempt: 1, latency_ms: 1, summary: {} },
  { stage: "intake_and_extract", agent: "intake", status: "succeeded", provider: "openai_compatible", model: "openai/gpt-oss-120b",
    attempt: 1, latency_ms: 1800, summary: {} },
];

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><I18nProvider>{ui}</I18nProvider></QueryClientProvider>);
}

afterEach(() => vi.unstubAllGlobals());

describe("AI status", () => {
  it("maps statuses and says plainly when rules were used", () => {
    expect(statusKey({ mode: "rules", reason: "no_consent" })).toBe("rules_no_consent");
    expect(statusKey({ mode: "rules", reason: "not_configured" })).toBe("rules_not_configured");
    wrap(<AiStatusBadge status={{ mode: "rules_fallback", reason: "LLM rate limit reached" }} />);
    expect(screen.getByRole("status")).toHaveTextContent(/AI unavailable right now — using built-in rules/);
  });

  it("names the model when AI answered", () => {
    wrap(<AiStatusBadge status={{ mode: "ai", model: "openai/gpt-oss-120b" }} />);
    expect(screen.getByRole("status")).toHaveTextContent("AI on: openai/gpt-oss-120b");
  });
});

describe("AgentTelemetry", () => {
  it("opens to show stages and the legal source read from the database", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      executions: TRACE, fetched_at: "2026-11-01T00:00:00Z",
      provenance: [{ rule: "limitation", grounded: true, section_ref: "Section 69", summary: null,
        document_title: "The Consumer Protection Act, 2019", source_url: "https://egazette.gov.in/x.pdf",
        chunk_id: "c1", in_knowledge_base: true, excerpt: "within two years from the date on which the cause of action has arisen" }],
    }), { status: 200 })));
    wrap(<AgentTelemetry caseId="case-1" lastTrace={TRACE} />);
    const toggle = screen.getByRole("button", { name: /live agent telemetry/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getAllByText("Understand & extract facts").length).toBeGreaterThan(0);
    expect(screen.getAllByText("openai/gpt-oss-120b").length).toBeGreaterThan(0);
    expect(await screen.findByText(/within two years/)).toBeInTheDocument();
    expect(screen.getByText("found in knowledge base")).toBeInTheDocument();
  });
});
