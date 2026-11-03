"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, AlertTriangle, BookCheck, ChevronDown, Cpu, ExternalLink, Sparkles } from "lucide-react";
import { useId, useState } from "react";

import { Badge } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { AgentTrace, AiStatus, TraceEntry } from "@/lib/types";
import { cn } from "@/lib/utils";

type StatusKey = "ai" | "ai_backup" | "ai_partial" | "rules_fallback" | "rules_no_consent" | "rules_not_configured";

export function statusKey(status: AiStatus): StatusKey {
  if (status.mode === "rules") return status.reason === "no_consent" ? "rules_no_consent" : "rules_not_configured";
  return status.mode ?? "rules_not_configured";
}

/** Says plainly whether the last reply came from the AI model, a backup model or the built-in rules. */
export function AiStatusBadge({ status }: { status: AiStatus | null }) {
  const { t } = useI18n();
  if (!status?.mode) return null;
  const key = statusKey(status);
  const tone = key === "ai" ? "success" : key === "ai_backup" || key === "ai_partial" || key === "rules_fallback" ? "warning" : "neutral";
  const Icon = key.startsWith("rules") ? Cpu : key === "ai" ? Sparkles : AlertTriangle;
  return (
    <Badge tone={tone} role="status">
      <Icon className="size-3" aria-hidden />
      {t(`telemetry.status.${key}`, { model: status.model ?? "" })}
    </Badge>
  );
}

function StageRow({ entry }: { entry: TraceEntry }) {
  const { t, dict } = useI18n();
  const label = (dict.telemetry.stages as Record<string, string>)[entry.stage] ?? entry.stage;
  const ai = !["rules", "n/a"].includes(entry.provider);
  return (
    <li className="flex flex-wrap items-center gap-x-2 gap-y-1 py-1.5 text-sm">
      <span className={cn("size-2 shrink-0 rounded-full", entry.status === "failed" ? "bg-danger-700" : ai ? "bg-success-700" : "bg-navy-600")} aria-hidden />
      <span className="font-medium">{label}</span>
      <code className="text-xs text-muted">{entry.stage}</code>
      <span className="ml-auto flex items-center gap-2 text-xs text-muted">
        {entry.status === "failed" ? <span className="text-danger-700">{t("telemetry.failed")}</span>
          : <span>{ai ? (entry.model ?? entry.provider) : t("telemetry.rules")}</span>}
        <span>{entry.latency_ms} ms</span>
      </span>
    </li>
  );
}

/** Collapsible drawer: the steps of the latest reply, recent runs, and each rule's legal source. */
export function AgentTelemetry({ caseId, lastTrace }: { caseId: string; lastTrace: TraceEntry[] }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const { data } = useQuery({
    queryKey: ["agent-trace", caseId],
    queryFn: () => api<AgentTrace>(`/cases/${caseId}/agent-trace?limit=30`),
    enabled: open,
  });

  return (
    <section className="rounded-xl border border-line bg-white">
      <button
        type="button"
        className="flex min-h-11 w-full items-center gap-2 px-4 py-2 text-left font-semibold text-navy-900"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((o) => !o)}
      >
        <Activity className="size-4 text-navy-700" aria-hidden />
        {t("telemetry.title")}
        <span className="ml-auto text-sm font-normal text-muted">{open ? t("telemetry.hide") : t("telemetry.show")}</span>
        <ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} aria-hidden />
      </button>
      {open && (
        <div id={panelId} className="space-y-4 border-t border-line px-4 py-3">
          <div>
            <h3 className="text-sm font-semibold">{t("telemetry.lastTurn")}</h3>
            {lastTrace.length ? (
              <ol className="divide-y divide-line">{lastTrace.map((e, i) => <StageRow key={`${e.agent}-${i}`} entry={e} />)}</ol>
            ) : <p className="text-sm text-muted">{t("telemetry.noRuns")}</p>}
          </div>
          {data && data.provenance.length > 0 && (
            <div>
              <h3 className="flex items-center gap-2 text-sm font-semibold"><BookCheck className="size-4" aria-hidden />{t("telemetry.provenance")}</h3>
              <ul className="mt-2 space-y-2">
                {data.provenance.map((p, i) => (
                  <li key={`${p.rule}-${i}`} className="rounded-lg bg-canvas p-3 text-sm">
                    <div className="flex flex-wrap items-center gap-2">
                      <code className="text-xs">{p.rule}</code>
                      <span className="font-medium">{p.section_ref}</span>
                      <Badge tone={p.in_knowledge_base ? "success" : "danger"}>{p.in_knowledge_base ? t("telemetry.inKb") : t("telemetry.notInKb")}</Badge>
                      {p.source_url && (
                        <a href={p.source_url} target="_blank" rel="noopener noreferrer" className="ml-auto inline-flex items-center gap-1 text-navy-700 underline">
                          {p.document_title}<ExternalLink className="size-3" aria-hidden />
                        </a>
                      )}
                    </div>
                    {p.excerpt && <p className="mt-1 text-muted">“{p.excerpt}…”</p>}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {data && (
            <div>
              <h3 className="text-sm font-semibold">{t("telemetry.history")}</h3>
              <ol className="max-h-64 divide-y divide-line overflow-y-auto">
                {data.executions.map((e, i) => <StageRow key={`${e.created_at}-${i}`} entry={e} />)}
              </ol>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
