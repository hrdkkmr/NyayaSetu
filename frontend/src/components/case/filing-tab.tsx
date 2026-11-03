"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ClipboardCopy, Download, ExternalLink, Info, Lock, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Alert, Badge, Card, CardBody, CardHeader, CardTitle, Checkbox, Field, Input, Label, Skeleton } from "@/components/ui/primitives";
import { api, ApiError, download } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { FilingOverview } from "@/lib/types";
import { formatDate } from "@/lib/utils";

export function FilingTab({ caseId }: { caseId: string }) {
  const { t, lang } = useI18n();
  const qc = useQueryClient();
  const [accepted, setAccepted] = useState(false);
  const [assist, setAssist] = useState(false);
  const [ack, setAck] = useState({ number: "", date: new Date().toISOString().slice(0, 10) });
  const { data, isLoading } = useQuery({ queryKey: ["filing", caseId], queryFn: () => api<FilingOverview>(`/cases/${caseId}/filing`) });
  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["filing", caseId] });
    void qc.invalidateQueries({ queryKey: ["case", caseId] });
    void qc.invalidateQueries({ queryKey: ["updates", caseId] });
  };
  const onError = (e: unknown) => toast.error(e instanceof ApiError ? e.message : t("common.errorGeneric"));

  const authorize = useMutation({
    mutationFn: () => api(`/cases/${caseId}/filing/authorize`, { method: "POST", body: { statement_accepted: accepted, allow_browser_assist: assist } }),
    onSuccess: invalidate, onError,
  });
  const copilot = useMutation({
    mutationFn: (filingId: string) => download(`/cases/${caseId}/filing/${filingId}/copilot-bundle`, "nyayasetu-copilot.zip"),
    onError,
  });
  const start = useMutation({
    mutationFn: (mode: "guided" | "browser_assist") => api(`/cases/${caseId}/filing/start`, { method: "POST", body: { mode } }),
    onSuccess: invalidate, onError,
  });
  const checklist = useMutation({
    mutationFn: ({ key, done }: { key: string; done: boolean }) =>
      api(`/cases/${caseId}/filing/${data!.record!.id}/checklist`, { method: "POST", body: { key, done } }),
    onSuccess: invalidate,
  });
  const saveAck = useMutation({
    mutationFn: () => api(`/cases/${caseId}/filing/${data!.record!.id}/acknowledgement`, {
      method: "POST", body: { acknowledgement_number: ack.number, submitted_on: ack.date },
    }),
    onSuccess: () => { toast.success(t("settings.saved")); invalidate(); }, onError,
  });

  if (isLoading || !data) return <Skeleton className="h-64" />;
  const record = data.record;
  const submitted = record && ["submitted_user_reported", "verified"].includes(record.status);

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <div className="space-y-4 lg:col-span-2">
        <Alert tone="info" title={t("filing.title")}>{t("filing.portalNote")}</Alert>

        {submitted && record ? (
          <Card>
            <CardBody className="space-y-2">
              <p className="flex items-center gap-2 text-lg font-semibold text-success-700"><CheckCircle2 aria-hidden />{record.acknowledgement_number}</p>
              <p>{record.status === "verified" ? t("filing.verified") : t("filing.reported")}</p>
              <p className="text-sm text-muted">{formatDate(record.submitted_at, lang)}</p>
            </CardBody>
          </Card>
        ) : !data.ready ? (
          <Alert tone="warning" title={t("filing.notReady")}>
            <ul className="list-disc pl-5">{data.blockers.map((b) => <li key={b}>{b}</li>)}</ul>
          </Alert>
        ) : !data.authorized ? (
          <Card>
            <CardHeader><CardTitle>{t("filing.authorizeTitle")}</CardTitle></CardHeader>
            <CardBody className="space-y-3">
              <p className="rounded-lg bg-canvas p-3">{data.authorization_statement}</p>
              <div className="flex items-start gap-3">
                <Checkbox id="auth-accept" checked={accepted} onCheckedChange={(c) => setAccepted(c === true)} />
                <Label htmlFor="auth-accept" className="font-normal">{t("filing.authorize")}</Label>
              </div>
              <div className="flex items-start gap-3">
                <Checkbox id="auth-assist" checked={assist} onCheckedChange={(c) => setAssist(c === true)} />
                <Label htmlFor="auth-assist" className="font-normal">{t("filing.allowAssist")}</Label>
              </div>
              <Button onClick={() => authorize.mutate()} disabled={!accepted} loading={authorize.isPending}><Lock aria-hidden />{t("filing.authorize")}</Button>
            </CardBody>
          </Card>
        ) : !record ? (
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => start.mutate("guided")} loading={start.isPending}>{t("filing.start")}</Button>
            {data.capabilities.browser_assist && <Button variant="secondary" onClick={() => start.mutate("browser_assist")}>Browser assist</Button>}
          </div>
        ) : null}

        {(record || data.authorized) && (
          <Card>
            <CardHeader>
              <CardTitle>{t("filing.steps")}</CardTitle>
              <Button asChild size="sm" variant="secondary">
                <a href={data.portal_url} target="_blank" rel="noopener noreferrer">{t("filing.openPortal")}<ExternalLink aria-hidden /></a>
              </Button>
            </CardHeader>
            <CardBody>
              <ol className="space-y-3">
                {data.guided_steps.map((s, i) => {
                  const done = !!record?.checklist_state?.[s.key];
                  return (
                    <li key={s.key} className="flex gap-3">
                      <Checkbox id={`step-${s.key}`} checked={done} disabled={!record}
                                onCheckedChange={(c) => checklist.mutate({ key: s.key, done: c === true })} />
                      <div>
                        <Label htmlFor={`step-${s.key}`} className={done ? "text-muted line-through" : ""}>{i + 1}. {s.title}</Label>
                        <p className="text-sm text-muted">{s.detail}</p>
                      </div>
                    </li>
                  );
                })}
              </ol>
              <p className="mt-3 text-sm text-muted">
                {t("filing.uploadRules", { date: data.upload_rules.observed_on, formats: data.upload_rules.formats.join(", "), mb: data.upload_rules.max_file_mb })}
              </p>
            </CardBody>
          </Card>
        )}

        {record && !submitted && (
          <Card>
            <CardHeader><CardTitle>{t("filing.copilotTitle")}</CardTitle></CardHeader>
            <CardBody className="space-y-3">
              <p>{t("filing.copilotBody")}</p>
              <p className="text-sm text-muted">{t("filing.copilotNote")}</p>
              <Button variant="secondary" loading={copilot.isPending} onClick={() => copilot.mutate(record.id)}>
                <Download aria-hidden />{t("filing.copilotDownload")}
              </Button>
            </CardBody>
          </Card>
        )}

        {record && !submitted && (
          <Card>
            <CardHeader><CardTitle>{t("filing.ackTitle")}</CardTitle></CardHeader>
            <CardBody>
              <p className="mb-3 text-muted">{t("filing.ackBody")}</p>
              <form className="grid gap-3 sm:grid-cols-[1fr_auto_auto] sm:items-end" onSubmit={(e) => { e.preventDefault(); saveAck.mutate(); }}>
                <Field id="ack-number" label={t("filing.ackNumber")}>
                  <Input id="ack-number" required minLength={3} value={ack.number} onChange={(e) => setAck({ ...ack, number: e.target.value })} />
                </Field>
                <Field id="ack-date" label={t("filing.submittedOn")}>
                  <Input id="ack-date" type="date" required value={ack.date} max={new Date().toISOString().slice(0, 10)}
                         onChange={(e) => setAck({ ...ack, date: e.target.value })} />
                </Field>
                <Button type="submit" loading={saveAck.isPending}>{t("filing.ackSave")}</Button>
              </form>
            </CardBody>
          </Card>
        )}
      </div>

      <div className="space-y-4">
        <Card>
          <CardHeader><CardTitle>{t("filing.dataSheet")}</CardTitle></CardHeader>
          <CardBody>
            <dl className="space-y-2">
              {data.data_sheet.map((row) => (
                <div key={row.key} className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <dt className="text-xs text-muted">{row.label}</dt>
                    <dd className="break-words font-medium">{row.value || <Badge tone="warning">{t("filing.missingValue")}</Badge>}</dd>
                  </div>
                  {row.value && (
                    <Button size="icon" variant="ghost" aria-label={`Copy ${row.label}`}
                            onClick={() => navigator.clipboard?.writeText(row.value).then(() => toast.success("Copied"))}>
                      <ClipboardCopy />
                    </Button>
                  )}
                </div>
              ))}
            </dl>
          </CardBody>
        </Card>
        <Card>
          <CardHeader><CardTitle>{t("filing.capability")}</CardTitle></CardHeader>
          <CardBody className="space-y-2 text-sm">
            <p className="flex gap-2"><ShieldCheck className="size-4 shrink-0 text-success-700" aria-hidden />Guided filing</p>
            <p className="flex gap-2"><Info className="size-4 shrink-0 text-muted" aria-hidden />{t("filing.noApi")}</p>
            {data.capabilities.notes.slice(1).map((n) => <p key={n} className="text-muted">{n}</p>)}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
