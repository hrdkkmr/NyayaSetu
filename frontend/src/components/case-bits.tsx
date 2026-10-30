"use client";

import { CalendarClock, ExternalLink } from "lucide-react";

import { Badge } from "@/components/ui/primitives";
import { useI18n } from "@/lib/i18n";
import type { Basis, Deadline } from "@/lib/types";
import { daysUntil, formatDate } from "@/lib/utils";

const STATUS_TONE: Record<string, "info" | "success" | "warning" | "danger" | "neutral" | "accent"> = {
  intake: "info", research: "info", planning: "info", drafting: "info", review: "warning",
  awaiting_approval: "warning", ready_to_file: "accent", filed_user_reported: "success", filed_verified: "success",
  needs_professional_review: "danger", closed: "neutral", archived: "neutral",
};

export function StatusBadge({ status }: { status: string }) {
  const { dict } = useI18n();
  const label = (dict.case.statuses as Record<string, string>)[status] ?? status;
  return <Badge tone={STATUS_TONE[status] ?? "neutral"}>{label}</Badge>;
}

export function CategoryLabel({ category }: { category: string | null }) {
  const { dict } = useI18n();
  if (!category) return <span className="text-muted">{dict.case.categories.unclear}</span>;
  return <>{(dict.case.categories as Record<string, string>)[category] ?? category}</>;
}

export function DeadlineChip({ deadline }: { deadline: Deadline }) {
  const { t, lang } = useI18n();
  const days = daysUntil(deadline.due_date);
  const tone = days < 0 ? "danger" : days <= 30 ? "warning" : "info";
  const label = days < 0 ? t("dashboard.overdue") : days === 0 ? t("dashboard.today") : t("dashboard.daysLeft", { n: days });
  return (
    <div className="flex items-start gap-3">
      <CalendarClock className="mt-0.5 size-5 shrink-0 text-navy-700" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="font-medium text-ink">{deadline.title}</p>
        <p className="text-sm text-muted">
          {formatDate(deadline.due_date, lang)}
          {deadline.is_estimate && <> · {t("common.estimate")}</>}
        </p>
      </div>
      <Badge tone={tone}>{label}</Badge>
    </div>
  );
}

export function SourceLink({ basis }: { basis: Basis }) {
  if (!basis.source_url) return <span className="text-sm text-muted">{basis.section_ref}</span>;
  return (
    <a
      href={basis.source_url}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 text-sm font-medium text-navy-700 underline"
      title={basis.document_title ?? undefined}
    >
      {basis.section_ref}, {shortTitle(basis.document_title ?? basis.document_key)}
      <ExternalLink className="size-3.5" aria-hidden />
    </a>
  );
}

export function shortTitle(title: string): string {
  if (title.startsWith("The Consumer Protection Act, 2019")) return "Consumer Protection Act, 2019";
  if (title.includes("Jurisdiction")) return "CP Jurisdiction Rules, 2021";
  if (title.includes("(Amendment) Rules, 2023")) return "CDRC (Amendment) Rules, 2023";
  return title.length > 60 ? `${title.slice(0, 57)}…` : title;
}
