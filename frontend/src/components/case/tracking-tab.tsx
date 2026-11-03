"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, CalendarPlus, CircleUserRound, Cpu, Download, History } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { DeadlineChip } from "@/components/case-bits";
import { Button } from "@/components/ui/button";
import { Alert, Badge, Card, CardBody, CardHeader, CardTitle, Field, Input, Select } from "@/components/ui/primitives";
import { api, ApiError, download } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { CaseDetail, CaseUpdate } from "@/lib/types";
import { formatDate } from "@/lib/utils";

const SOURCE_ICON = { official_portal: BadgeCheck, user_reported: CircleUserRound, internal: Cpu };
const SOURCE_TONE = { official_portal: "success", user_reported: "accent", internal: "neutral" } as const;

export function TrackingTab({ detail }: { detail: CaseDetail }) {
  const { t, lang, dict } = useI18n();
  const qc = useQueryClient();
  const caseId = detail.case.id;
  const [form, setForm] = useState({ update_type: "hearing", title: "", event_date: "" });
  const { data: updates } = useQuery({ queryKey: ["updates", caseId], queryFn: () => api<CaseUpdate[]>(`/cases/${caseId}/updates`) });
  const add = useMutation({
    mutationFn: () => api(`/cases/${caseId}/updates`, {
      method: "POST", body: { ...form, event_date: form.event_date || null },
    }),
    onSuccess: () => {
      setForm({ update_type: "hearing", title: "", event_date: "" });
      void qc.invalidateQueries({ queryKey: ["updates", caseId] });
      void qc.invalidateQueries({ queryKey: ["case", caseId] });
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : t("common.errorGeneric")),
  });
  const [noticeDate, setNoticeDate] = useState("");
  const addNotice = useMutation({
    mutationFn: () => api(`/cases/${caseId}/deadlines`, {
      method: "POST", body: { title: t("tracking.noticeDefaultTitle"), due_date: noticeDate, kind: "legal_notice" },
    }),
    onSuccess: () => {
      setNoticeDate("");
      void qc.invalidateQueries({ queryKey: ["case", caseId] });
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : t("common.errorGeneric")),
  });
  const exportCalendar = async () => {
    try {
      await download(`/cases/${caseId}/deadlines.ics`, `nyayasetu-${detail.case.reference}.ics`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t("common.errorGeneric"));
    }
  };
  const done = useMutation({
    mutationFn: (id: string) => api(`/cases/${caseId}/deadlines/${id}`, { method: "PATCH", body: { status: "done" } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["case", caseId] }),
  });

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <div className="space-y-4 lg:col-span-2">
        <Alert tone="info">{t("tracking.note")}</Alert>
        <Card>
          <CardHeader><CardTitle>{t("tracking.title")}</CardTitle></CardHeader>
          <CardBody>
            {!updates?.length ? <p className="text-muted">{t("tracking.noUpdates")}</p> : (
              <ol className="space-y-4 border-l-2 border-navy-100 pl-4">
                {updates.map((u) => {
                  const Icon = SOURCE_ICON[u.source];
                  return (
                    <li key={u.id}>
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="font-semibold">{u.title}</p>
                        <Badge tone={SOURCE_TONE[u.source]}><Icon className="size-3" aria-hidden />{dict.tracking.sources[u.source]}</Badge>
                      </div>
                      {u.body && <p className="text-sm">{u.body}</p>}
                      <p className="text-xs text-muted">
                        {u.event_date ? formatDate(u.event_date, lang) : formatDate(u.created_at, lang)}
                        {u.source_reference && <> · {u.source_reference}</>}
                      </p>
                    </li>
                  );
                })}
              </ol>
            )}
          </CardBody>
        </Card>
      </div>
      <div className="space-y-4">
        <Card>
          <CardHeader><CardTitle>{t("tracking.addUpdate")}</CardTitle></CardHeader>
          <CardBody>
            <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
              <Field id="u-type" label={t("tracking.updateType")}>
                <Select id="u-type" value={form.update_type} onChange={(e) => setForm({ ...form, update_type: e.target.value })}>
                  {Object.entries(dict.tracking.types).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </Select>
              </Field>
              <Field id="u-title" label={t("tracking.titleLabel")}>
                <Input id="u-title" required minLength={2} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
              </Field>
              <Field id="u-date" label={t("tracking.dateLabel")}>
                <Input id="u-date" type="date" value={form.event_date} onChange={(e) => setForm({ ...form, event_date: e.target.value })} />
              </Field>
              <Button type="submit" className="w-full" loading={add.isPending}>{t("common.save")}</Button>
            </form>
          </CardBody>
        </Card>
        <Card>
          <CardHeader><CardTitle>{t("case.deadlines")}</CardTitle></CardHeader>
          <CardBody>
            {detail.deadlines.length === 0 ? <p className="text-muted">{t("dashboard.noDeadlines")}</p> : (
              <ul className="space-y-3">
                {detail.deadlines.map((d) => (
                  <li key={d.id}>
                    <DeadlineChip deadline={d} />
                    {d.basis && <p className="ml-8 text-xs text-muted">{d.basis}</p>}
                    {d.status === "open" && d.google_calendar_url && (
                      <a href={d.google_calendar_url} target="_blank" rel="noopener noreferrer"
                         className="ml-8 inline-flex min-h-11 items-center gap-1 text-sm text-navy-700 underline">
                        <CalendarPlus className="size-4" aria-hidden />{t("tracking.googleCalendar")}
                      </a>
                    )}
                    {d.status === "open" && <Button size="sm" variant="link" className="ml-8" onClick={() => done.mutate(d.id)}>{t("tracking.markDone")}</Button>}
                    {d.status !== "open" && <p className="ml-8 text-xs text-muted">{d.status}</p>}
                  </li>
                ))}
              </ul>
            )}
            {detail.deadlines.some((d) => d.status === "open") && (
              <Button size="sm" variant="secondary" className="mt-3 w-full" onClick={() => void exportCalendar()}>
                <Download aria-hidden />{t("tracking.calendarDownload")}
              </Button>
            )}
          </CardBody>
        </Card>
        <Card>
          <CardHeader><CardTitle>{t("tracking.noticeTitle")}</CardTitle></CardHeader>
          <CardBody>
            <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); addNotice.mutate(); }}>
              <p className="text-sm text-muted">{t("tracking.noticeHint")}</p>
              <Field id="notice-date" label={t("tracking.noticeDate")}>
                <Input id="notice-date" type="date" required value={noticeDate} onChange={(e) => setNoticeDate(e.target.value)} />
              </Field>
              <Button type="submit" className="w-full" loading={addNotice.isPending} disabled={!noticeDate}>{t("common.save")}</Button>
            </form>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

export function ActivityTab({ caseId }: { caseId: string }) {
  const { t, lang } = useI18n();
  const { data } = useQuery({
    queryKey: ["activity", caseId],
    queryFn: () => api<{ id: string; action: string; actor_type: string; outcome: string; created_at: string }[]>(`/cases/${caseId}/activity`),
  });
  return (
    <Card>
      <CardHeader><CardTitle>{t("case.tabs.activity")}</CardTitle></CardHeader>
      <CardBody>
        {!data?.length ? <p className="text-muted">—</p> : (
          <ul className="divide-y divide-line">
            {data.map((a) => (
              <li key={a.id} className="flex items-center gap-3 py-2 text-sm">
                <History className="size-4 text-muted" aria-hidden />
                <span className="font-medium">{a.action}</span>
                <Badge tone={a.outcome === "success" ? "neutral" : "danger"}>{a.actor_type}</Badge>
                <span className="ml-auto text-muted">{formatDate(a.created_at, lang)} {new Date(a.created_at).toLocaleTimeString(lang === "hi" ? "hi-IN" : "en-IN", { hour: "2-digit", minute: "2-digit" })}</span>
              </li>
            ))}
          </ul>
        )}
      </CardBody>
    </Card>
  );
}
