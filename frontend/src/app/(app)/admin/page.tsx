"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Alert, Badge, Card, CardBody, CardHeader, CardTitle, Skeleton, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import type { LegalDoc } from "@/lib/types";
import { formatDate } from "@/lib/utils";

type Row = Record<string, unknown>;

function useAdmin<T>(key: string, path: string, enabled: boolean) {
  return useQuery({ queryKey: ["admin", key], queryFn: () => api<T>(path), enabled });
}

function Table({ rows, columns }: { rows: Row[] | undefined; columns: string[] }) {
  if (!rows) return <Skeleton className="h-32" />;
  if (!rows.length) return <p className="text-muted">—</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead><tr>{columns.map((c) => <th key={c} className="border-b border-line px-2 py-2 font-semibold">{c}</th>)}</tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-line align-top">
              {columns.map((c) => (
                <td key={c} className="max-w-xs break-words px-2 py-2">
                  {typeof r[c] === "object" && r[c] !== null ? <code className="text-xs">{JSON.stringify(r[c])}</code> : String(r[c] ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function AdminPage() {
  const { t, lang, dict } = useI18n();
  const { user } = useAuth();
  const qc = useQueryClient();
  const isAdmin = user?.role === "admin";
  const overview = useAdmin<Record<string, number>>("overview", "/admin/overview", isAdmin);
  const health = useAdmin<Record<string, { status: "ok" | "error" | "not_configured"; detail: string }>>("health", "/admin/health", isAdmin);
  const sources = useAdmin<(LegalDoc & { ingestion_error: string | null })[]>("sources", "/admin/legal-sources", isAdmin);
  const jobs = useAdmin<Row[]>("jobs", "/admin/jobs", isAdmin);
  const agents = useAdmin<Row[]>("agents", "/admin/agent-executions", isAdmin);
  const workflows = useAdmin<Row[]>("workflows", "/admin/workflows", isAdmin);
  const audit = useAdmin<Row[]>("audit", "/admin/audit", isAdmin);

  const ingest = useMutation({
    mutationFn: () => api("/admin/legal-sources/ingest?force=true", { method: "POST" }),
    onSuccess: () => { toast.success("Ingestion started"); void qc.invalidateQueries({ queryKey: ["admin"] }); },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : t("common.errorGeneric")),
  });

  if (!isAdmin) return <Alert tone="danger">403</Alert>;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold text-navy-900">{t("admin.title")}</h1>
        <Button variant="secondary" size="sm" onClick={() => qc.invalidateQueries({ queryKey: ["admin"] })}><RefreshCw aria-hidden />Refresh</Button>
      </div>
      <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {overview.data && Object.entries(overview.data).map(([k, v]) => (
          <Card key={k}><CardBody><p className="text-2xl font-bold text-navy-900">{v}</p><p className="text-sm text-muted">{k.replace(/_/g, " ")}</p></CardBody></Card>
        ))}
      </div>
      <Tabs defaultValue="health">
        <TabsList>
          <TabsTrigger value="health">{t("admin.health")}</TabsTrigger>
          <TabsTrigger value="sources">{t("admin.sources")}</TabsTrigger>
          <TabsTrigger value="jobs">{t("admin.jobs")}</TabsTrigger>
          <TabsTrigger value="agents">{t("admin.agents")}</TabsTrigger>
          <TabsTrigger value="workflows">{t("admin.workflows")}</TabsTrigger>
          <TabsTrigger value="audit">{t("admin.audit")}</TabsTrigger>
        </TabsList>
        <TabsContent value="health">
          <Card><CardBody>
            {!health.data ? <Skeleton className="h-32" /> : (
              <ul className="divide-y divide-line">
                {Object.entries(health.data).map(([k, v]) => (
                  <li key={k} className="flex flex-wrap items-center gap-3 py-2">
                    <span className="w-48 font-semibold">{k}</span>
                    <Badge tone={v.status === "ok" ? "success" : v.status === "error" ? "danger" : "neutral"}>{dict.admin.status[v.status]}</Badge>
                    <span className="text-sm text-muted">{v.detail}</span>
                  </li>
                ))}
              </ul>
            )}
          </CardBody></Card>
        </TabsContent>
        <TabsContent value="sources">
          <Card>
            <CardHeader><CardTitle>{t("admin.sources")}</CardTitle><Button size="sm" onClick={() => ingest.mutate()} loading={ingest.isPending}>{t("admin.ingest")}</Button></CardHeader>
            <CardBody>
              <ul className="divide-y divide-line">
                {sources.data?.map((d) => (
                  <li key={d.key} className="space-y-1 py-3 text-sm">
                    <p className="font-semibold">{d.title}</p>
                    <p className="text-muted">{d.ingestion_status} · {d.chunk_count} chunks · {d.verification_status} · retrieved {formatDate(d.retrieved_at, lang)}</p>
                    {d.ingestion_error && <Alert tone="danger">{d.ingestion_error}</Alert>}
                  </li>
                ))}
              </ul>
            </CardBody>
          </Card>
        </TabsContent>
        <TabsContent value="jobs"><Card><CardBody><Table rows={jobs.data} columns={["kind", "status", "attempts", "error", "created_at", "finished_at"]} /></CardBody></Card></TabsContent>
        <TabsContent value="agents"><Card><CardBody><Table rows={agents.data} columns={["agent", "status", "provider", "attempt", "latency_ms", "error", "created_at"]} /></CardBody></Card></TabsContent>
        <TabsContent value="workflows"><Card><CardBody><Table rows={workflows.data} columns={["case_id", "status", "phase", "revision", "last_error", "updated_at"]} /></CardBody></Card></TabsContent>
        <TabsContent value="audit"><Card><CardBody><Table rows={audit.data} columns={["action", "actor_type", "resource_type", "outcome", "meta", "created_at"]} /></CardBody></Card></TabsContent>
      </Tabs>
    </div>
  );
}
