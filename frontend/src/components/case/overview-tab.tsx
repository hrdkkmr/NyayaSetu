"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Circle, CircleDot, FileText, RefreshCw, Route, SkipForward } from "lucide-react";
import { toast } from "sonner";

import { CategoryLabel, DeadlineChip, SourceLink } from "@/components/case-bits";
import { Button } from "@/components/ui/button";
import { Alert, Badge, Card, CardBody, CardHeader, CardTitle } from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { CaseDetail } from "@/lib/types";
import { formatDate, formatINR } from "@/lib/utils";

const STEP_ICON = { done: CheckCircle2, in_progress: CircleDot, pending: Circle, blocked: AlertTriangle, skipped: SkipForward };

export function OverviewTab({ detail, onGoTo }: { detail: CaseDetail; onGoTo: (tab: string) => void }) {
  const { t, lang, dict } = useI18n();
  const qc = useQueryClient();
  const c = detail.case;
  const outcomes = detail.analysis.rule_outcomes ?? {};
  const labelFor = (key: string) => {
    const k = detail.fact_keys.find((f) => f.key === key);
    return k ? (lang === "hi" ? k.label_hi : k.label_en) : key;
  };

  const refresh = useMutation({
    mutationFn: () => api(`/cases/${c.id}/analysis/refresh`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["case", c.id] }),
    onError: (e) => toast.error(e instanceof ApiError ? e.message : t("common.errorGeneric")),
  });
  const generate = useMutation({
    mutationFn: () => api<{ reply: string }>(`/cases/${c.id}/drafts/generate`, { method: "POST" }),
    onSuccess: (r) => {
      toast.success(r.reply);
      qc.invalidateQueries({ queryKey: ["case", c.id] });
      qc.invalidateQueries({ queryKey: ["drafts", c.id] });
      onGoTo("documents");
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : t("common.errorGeneric")),
  });
  const toggleStep = useMutation({
    mutationFn: ({ key, done }: { key: string; done: boolean }) =>
      api(`/cases/${c.id}/workflow/steps/${key}?status=${done ? "done" : "pending"}`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["case", c.id] }),
  });

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <div className="space-y-4 lg:col-span-2">
        {c.requires_human_review && <Alert tone="warning">{t("case.humanReview")}</Alert>}
        <Card>
          <CardHeader><CardTitle>{t("case.summary")}</CardTitle></CardHeader>
          <CardBody className="space-y-4">
            <p className="whitespace-pre-wrap">{detail.summary ?? t("common.unknown")}</p>
            <dl className="grid gap-3 sm:grid-cols-2">
              <div><dt className="text-sm text-muted">{t("case.category")}</dt><dd className="font-medium"><CategoryLabel category={c.category} /></dd></div>
              <div><dt className="text-sm text-muted">{t("case.amount")}</dt><dd className="font-medium">{formatINR(c.financial_amount)}</dd></div>
              <div><dt className="text-sm text-muted">{t("case.incidentDate")}</dt><dd className="font-medium">{formatDate(c.incident_date, lang)}</dd></div>
              <div><dt className="text-sm text-muted">{t("case.location")}</dt><dd className="font-medium">{[c.location_district, c.location_state].filter(Boolean).join(", ") || "—"}</dd></div>
            </dl>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t("case.analysis")}</CardTitle>
            {Object.keys(outcomes).length > 0 && (
              <Button size="sm" variant="ghost" onClick={() => refresh.mutate()} loading={refresh.isPending}>
                <RefreshCw aria-hidden /> {t("case.refresh")}
              </Button>
            )}
          </CardHeader>
          <CardBody>
            {Object.keys(outcomes).length === 0 ? (
              <p className="text-muted">{detail.missing_information.length ? t("case.missing") + ": " + detail.missing_information.map(labelFor).join(", ") : "—"}</p>
            ) : (
              <ul className="space-y-4">
                {["consumer_status", "pecuniary_forum", "territorial_options", "limitation", "filing_fee", "available_reliefs", "appeal_period"]
                  .filter((k) => outcomes[k])
                  .map((k) => {
                    const o = outcomes[k];
                    return (
                      <li key={k} className="border-l-4 border-navy-100 pl-3">
                        <p>{lang === "hi" ? o.explanation_hi : o.explanation_en}</p>
                        <div className="mt-1 flex flex-wrap gap-x-3">
                          {o.basis.map((b) => <SourceLink key={b.section_ref + b.document_key} basis={b} />)}
                          {!o.grounded && <Badge tone="warning">source not loaded</Badge>}
                        </div>
                        {o.caveats.length > 0 && <p className="mt-1 text-sm text-muted">{o.caveats.join(" ")}</p>}
                      </li>
                    );
                  })}
              </ul>
            )}
            <p className="mt-4 text-sm text-muted">{t("common.notAdvice")}</p>
          </CardBody>
        </Card>

        {(detail.analysis.potential_routes ?? []).length > 0 && (
          <Card>
            <CardHeader><CardTitle>{t("case.routes")}</CardTitle></CardHeader>
            <CardBody>
              <ul className="space-y-2">
                {detail.analysis.potential_routes!.map((r) => (
                  <li key={r.key} className="flex items-center gap-2">
                    <Route className="size-5 text-navy-700" aria-hidden />
                    {lang === "hi" ? r.title_hi : r.title_en}
                    {r.optional && <Badge>{t("common.optional")}</Badge>}
                  </li>
                ))}
              </ul>
            </CardBody>
          </Card>
        )}
      </div>

      <div className="space-y-4">
        <Card>
          <CardHeader><CardTitle>{t("case.nextSteps")}</CardTitle></CardHeader>
          <CardBody>
            {detail.workflow.steps.length === 0 ? <p className="text-muted">{t("case.missing")}</p> : (
              <ol className="space-y-3">
                {detail.workflow.steps.map((s) => {
                  const Icon = STEP_ICON[s.status];
                  return (
                    <li key={s.key} className="flex gap-3">
                      <Icon className={`mt-0.5 size-5 shrink-0 ${s.status === "done" ? "text-success-700" : s.status === "in_progress" ? "text-saffron-600" : "text-muted"}`} aria-hidden />
                      <div className="min-w-0 flex-1">
                        <p className={`font-medium ${s.status === "done" ? "text-muted line-through" : ""}`}>{lang === "hi" && s.title_hi ? s.title_hi : s.title}</p>
                        {s.description && s.status !== "done" && <p className="text-sm text-muted">{s.description}</p>}
                        <p className="text-xs text-muted">
                          {dict.case.stepStatus[s.status]} · {dict.case.owner[s.owner]}
                          {s.due_date && <> · {formatDate(s.due_date, lang)}</>}
                        </p>
                        {s.owner === "user" && s.status !== "done" && s.status !== "skipped" && (
                          <Button size="sm" variant="link" onClick={() => toggleStep.mutate({ key: s.key, done: true })}>{t("tracking.markDone")}</Button>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ol>
            )}
            <Button className="mt-4 w-full" onClick={() => generate.mutate()} loading={generate.isPending}
                    disabled={detail.missing_information.length > 0 || !outcomes.pecuniary_forum}>
              <FileText aria-hidden /> {t("case.generateDocs")}
            </Button>
            {detail.missing_information.length > 0 && (
              <p className="mt-2 text-sm text-muted">{t("case.missing")}: {detail.missing_information.map(labelFor).join(", ")}</p>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader><CardTitle>{t("case.deadlines")}</CardTitle></CardHeader>
          <CardBody>
            {detail.deadlines.length === 0 ? <p className="text-muted">{t("dashboard.noDeadlines")}</p> : (
              <ul className="space-y-3">
                {detail.deadlines.map((d) => <li key={d.id}><DeadlineChip deadline={d} />{d.basis && <p className="ml-8 text-xs text-muted">{d.basis}</p>}</li>)}
              </ul>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader><CardTitle>{t("case.parties")}</CardTitle></CardHeader>
          <CardBody>
            {detail.parties.length === 0 ? <p className="text-muted">{t("common.unknown")}</p> : (
              <ul className="space-y-3">
                {detail.parties.map((p) => (
                  <li key={p.role}>
                    <p className="text-sm text-muted">{p.role === "complainant" ? t("case.complainant") : t("case.oppositeParty")}</p>
                    <p className="font-medium">{p.name}</p>
                    {p.address && <p className="text-sm">{p.address}</p>}
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>

        {detail.incident_timeline.length > 0 && (
          <Card>
            <CardHeader><CardTitle>{t("case.timeline")}</CardTitle></CardHeader>
            <CardBody>
              <ol className="space-y-2 border-l-2 border-navy-100 pl-4">
                {detail.incident_timeline.map((e) => (
                  <li key={e.label}><p className="font-medium">{formatDate(e.date, lang)}</p><p className="text-sm text-muted">{e.label}</p></li>
                ))}
              </ol>
            </CardBody>
          </Card>
        )}
      </div>
    </div>
  );
}
