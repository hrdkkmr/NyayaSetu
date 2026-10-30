"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCircle2, FileText, FolderOpen, Keyboard, ListChecks, MessageSquare, Mic, Send } from "lucide-react";
import Link from "next/link";

import { CategoryLabel, DeadlineChip, StatusBadge } from "@/components/case-bits";
import { Button } from "@/components/ui/button";
import { Badge, Card, CardBody, CardHeader, CardTitle, EmptyState, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import type { Dashboard } from "@/lib/types";
import { formatDate, formatINR } from "@/lib/utils";

export default function DashboardPage() {
  const { t, lang } = useI18n();
  const { user } = useAuth();
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["dashboard"], queryFn: () => api<Dashboard>("/dashboard") });
  const markRead = useMutation({
    mutationFn: (id: string) => api(`/notifications/${id}/read`, { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      qc.invalidateQueries({ queryKey: ["notifications"] });
    },
  });

  if (isLoading || !data) {
    return <div className="grid gap-4 md:grid-cols-2"><Skeleton className="h-48" /><Skeleton className="h-48" /></div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-navy-900 md:text-3xl">{t("dashboard.greeting", { name: user?.full_name.split(" ")[0] ?? "" })}</h1>
          <p className="text-muted">{t("dashboard.title")}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button asChild size="lg"><Link href="/cases/new?mode=voice"><Mic aria-hidden />{t("dashboard.startVoice")}</Link></Button>
          <Button asChild size="lg" variant="secondary"><Link href="/cases/new?mode=text"><Keyboard aria-hidden />{t("dashboard.startText")}</Link></Button>
        </div>
      </div>

      {data.cases.length === 0 ? (
        <EmptyState
          icon={FolderOpen}
          title={t("dashboard.noCasesTitle")}
          body={t("dashboard.noCasesBody")}
          action={<Button asChild><Link href="/cases/new?mode=voice"><Mic aria-hidden />{t("dashboard.startVoice")}</Link></Button>}
        />
      ) : (
        <Card>
          <CardHeader><CardTitle>{t("dashboard.activeCases")}</CardTitle></CardHeader>
          <ul className="divide-y divide-line">
            {data.cases.map((c) => (
              <li key={c.id}>
                <Link href={`/cases/${c.id}`} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 hover:bg-navy-50">
                  <div className="min-w-0">
                    <p className="font-semibold text-navy-900">{c.title}</p>
                    <p className="text-sm text-muted">
                      {c.reference} · <CategoryLabel category={c.category} />
                      {c.financial_amount && <> · {formatINR(c.financial_amount)}</>} · {formatDate(c.updated_at, lang)}
                    </p>
                  </div>
                  <StatusBadge status={c.status} />
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>{t("dashboard.pending")}</CardTitle></CardHeader>
          <CardBody>
            {data.pending_actions.length === 0 ? <p className="text-muted">{t("dashboard.noPending")}</p> : (
              <ul className="space-y-3">
                {data.pending_actions.map((s) => (
                  <li key={`${s.case_id}-${s.key}`} className="flex items-start gap-3">
                    <ListChecks className="mt-0.5 size-5 text-navy-700" aria-hidden />
                    <div>
                      <Link href={`/cases/${s.case_id}`} className="font-medium text-navy-900 underline-offset-2 hover:underline">
                        {lang === "hi" && s.title_hi ? s.title_hi : s.title}
                      </Link>
                      <p className="text-sm text-muted">{s.case_title}</p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader><CardTitle>{t("dashboard.deadlines")}</CardTitle></CardHeader>
          <CardBody>
            {data.deadlines.length === 0 ? <p className="text-muted">{t("dashboard.noDeadlines")}</p> : (
              <ul className="space-y-4">
                {data.deadlines.map((d) => <li key={d.id}><DeadlineChip deadline={d} /><p className="ml-8 text-sm text-muted">{d.case_title}</p></li>)}
              </ul>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader><CardTitle>{t("dashboard.toReview")}</CardTitle></CardHeader>
          <CardBody>
            {data.documents_to_review.length === 0 ? <p className="text-muted">{t("dashboard.noReview")}</p> : (
              <ul className="space-y-3">
                {data.documents_to_review.map((d) => (
                  <li key={d.id} className="flex items-center gap-3">
                    <FileText className="size-5 text-navy-700" aria-hidden />
                    <Link href={`/cases/${d.case_id}/documents/${d.id}`} className="font-medium text-navy-900 hover:underline">{d.title}</Link>
                    <span className="text-sm text-muted">· {d.case_title}</span>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader><CardTitle>{t("dashboard.filings")}</CardTitle></CardHeader>
          <CardBody>
            {data.filings.length === 0 ? <p className="text-muted">{t("dashboard.noFilings")}</p> : (
              <ul className="space-y-3">
                {data.filings.map((f) => (
                  <li key={f.id} className="flex flex-wrap items-center gap-2">
                    <Send className="size-5 text-navy-700" aria-hidden />
                    <Link href={`/cases/${f.case_id}?tab=filing`} className="font-medium text-navy-900 hover:underline">{f.case_title}</Link>
                    <Badge tone={f.status === "verified" ? "success" : f.status === "submitted_user_reported" ? "accent" : "info"}>
                      {f.status === "verified" ? t("filing.verified") : f.status === "submitted_user_reported" ? t("tracking.sources.user_reported") : f.status}
                    </Badge>
                    {f.acknowledgement_number && <span className="text-sm text-muted">{f.acknowledgement_number}</span>}
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>

        <Card id="notifications">
          <CardHeader><CardTitle>{t("dashboard.notifications")}</CardTitle></CardHeader>
          <CardBody>
            {data.notifications.length === 0 ? <p className="text-muted">{t("dashboard.noNotifications")}</p> : (
              <ul className="space-y-3">
                {data.notifications.map((n) => (
                  <li key={n.id} className="flex items-start gap-3">
                    <Bell className={`mt-0.5 size-5 ${n.read ? "text-muted" : "text-saffron-600"}`} aria-hidden />
                    <div className="flex-1">
                      {n.link ? <Link href={n.link} className="font-medium hover:underline">{n.title}</Link> : <p className="font-medium">{n.title}</p>}
                      <p className="text-xs text-muted">{formatDate(n.created_at, lang)}</p>
                    </div>
                    {!n.read && (
                      <Button size="sm" variant="ghost" onClick={() => markRead.mutate(n.id)} aria-label="Mark as read">
                        <CheckCircle2 />
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader><CardTitle>{t("dashboard.recent")}</CardTitle></CardHeader>
          <CardBody>
            {data.recent_conversations.length === 0 ? <p className="text-muted">—</p> : (
              <ul className="space-y-3">
                {data.recent_conversations.map((c) => (
                  <li key={c.id} className="flex items-center gap-3">
                    <MessageSquare className="size-5 text-navy-700" aria-hidden />
                    <Link href={`/cases/${c.case_id}?tab=conversation`} className="font-medium hover:underline">{c.case_title}</Link>
                    <span className="text-sm text-muted">{formatDate(c.updated_at, lang)}</span>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
