"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, ArchiveRestore } from "lucide-react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { StatusBadge } from "@/components/case-bits";
import { DocumentsTab } from "@/components/case/documents-tab";
import { FactsTab } from "@/components/case/facts-tab";
import { FilingTab } from "@/components/case/filing-tab";
import { OverviewTab } from "@/components/case/overview-tab";
import { ResearchTab } from "@/components/case/research-tab";
import { ActivityTab, TrackingTab } from "@/components/case/tracking-tab";
import { Conversation } from "@/components/conversation/conversation";
import { Button } from "@/components/ui/button";
import { Alert, Skeleton, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { CaseDetail, TurnResult } from "@/lib/types";

const TABS = ["overview", "conversation", "facts", "research", "documents", "filing", "tracking", "activity"] as const;

function CaseWorkspace() {
  const { id } = useParams<{ id: string }>();
  const params = useSearchParams();
  const router = useRouter();
  const qc = useQueryClient();
  const { t, dict } = useI18n();
  const initialTab = params.get("tab");
  const [tab, setTab] = useState<string>(TABS.includes(initialTab as (typeof TABS)[number]) ? initialTab! : "overview");
  const [initialTurn, setInitialTurn] = useState<TurnResult | null>(null);

  const { data, isLoading, error } = useQuery({ queryKey: ["case", id], queryFn: () => api<CaseDetail>(`/cases/${id}`) });
  const archive = useMutation({
    mutationFn: (archived: boolean) => api(`/cases/${id}/archive?archived=${archived}`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["case", id] }),
  });

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(`ns-turn-${id}`);
      if (raw) {
        setInitialTurn(JSON.parse(raw));
        sessionStorage.removeItem(`ns-turn-${id}`);
      }
    } catch {
      /* storage unavailable */
    }
  }, [id]);

  const changeTab = (next: string) => {
    setTab(next);
    const url = new URL(window.location.href);
    url.searchParams.set("tab", next);
    url.searchParams.delete("mode");
    router.replace(url.pathname + url.search, { scroll: false });
  };

  if (isLoading) return <div className="space-y-4"><Skeleton className="h-10 w-72" /><Skeleton className="h-64" /></div>;
  if (error || !data) {
    return <Alert tone="danger">{error instanceof ApiError && error.status === 404 ? t("errors.notFound") : t("common.errorGeneric")}</Alert>;
  }
  const c = data.case;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm text-muted">{t("case.reference")}: {c.reference}</p>
          <h1 className="text-2xl font-bold text-navy-900 md:text-3xl">{c.title}</h1>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={c.status} />
          <Button size="sm" variant="ghost" onClick={() => archive.mutate(!c.archived)}>
            {c.archived ? <ArchiveRestore aria-hidden /> : <Archive aria-hidden />}
            <span className="hidden sm:inline">{c.archived ? t("case.unarchive") : t("case.archive")}</span>
          </Button>
        </div>
      </div>
      {data.workflow.last_error && <Alert tone="warning">{t("common.errorGeneric")}</Alert>}

      <Tabs value={tab} onValueChange={changeTab}>
        <TabsList aria-label="Case sections">
          {TABS.map((k) => <TabsTrigger key={k} value={k}>{dict.case.tabs[k]}</TabsTrigger>)}
        </TabsList>
        <TabsContent value="overview"><OverviewTab detail={data} onGoTo={changeTab} /></TabsContent>
        <TabsContent value="conversation">
          <div className="mx-auto max-w-3xl">
            <Conversation caseId={id} initialMode={params.get("mode") === "voice" ? "voice" : "text"} initialTurn={initialTurn} />
          </div>
        </TabsContent>
        <TabsContent value="facts"><FactsTab detail={data} /></TabsContent>
        <TabsContent value="research"><ResearchTab caseId={id} /></TabsContent>
        <TabsContent value="documents"><DocumentsTab caseId={id} reference={c.reference} /></TabsContent>
        <TabsContent value="filing"><FilingTab caseId={id} /></TabsContent>
        <TabsContent value="tracking"><TrackingTab detail={data} /></TabsContent>
        <TabsContent value="activity"><ActivityTab caseId={id} /></TabsContent>
      </Tabs>
    </div>
  );
}

export default function CasePage() {
  return <Suspense><CaseWorkspace /></Suspense>;
}
