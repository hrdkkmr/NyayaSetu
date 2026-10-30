"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileCheck2, FileText, FileUp, ListPlus, Loader2, ShieldAlert, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Alert, Badge, Card, CardBody, CardHeader, CardTitle, EmptyState } from "@/components/ui/primitives";
import { api, ApiError, download } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import type { Evidence, GeneratedDoc, Upload } from "@/lib/types";
import { formatDate } from "@/lib/utils";

const ACCEPTABLE = new Set(["amount_paid", "purchase_date", "seller_name"]);

export function DocumentsTab({ caseId, reference }: { caseId: string; reference: string }) {
  const { t, lang, dict } = useI18n();
  const { user } = useAuth();
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const onError = (e: unknown) => toast.error(e instanceof ApiError ? e.message : t("common.errorGeneric"));

  const uploads = useQuery({
    queryKey: ["uploads", caseId],
    queryFn: () => api<Upload[]>(`/cases/${caseId}/uploads`),
    refetchInterval: (q) => (q.state.data?.some((u) => ["uploaded", "processing"].includes(u.status)) ? 2000 : false),
  });
  const evidence = useQuery({ queryKey: ["evidence", caseId], queryFn: () => api<Evidence[]>(`/cases/${caseId}/evidence`) });
  const drafts = useQuery({ queryKey: ["drafts", caseId], queryFn: () => api<GeneratedDoc[]>(`/cases/${caseId}/drafts`) });

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["uploads", caseId] });
    void qc.invalidateQueries({ queryKey: ["evidence", caseId] });
    void qc.invalidateQueries({ queryKey: ["case", caseId] });
  };

  const onFile = async (file: File | undefined) => {
    if (!file) return;
    setUploading(true);
    const form = new FormData();
    form.append("file", file);
    try {
      await api(`/cases/${caseId}/uploads`, { method: "POST", body: form });
      invalidate();
    } catch (e) {
      onError(e);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const accept = useMutation({
    mutationFn: ({ id, field }: { id: string; field: string }) =>
      api(`/cases/${caseId}/uploads/${id}/accept-fields`, { method: "POST", body: { fields: [field] } }),
    onSuccess: () => { toast.success(t("settings.saved")); invalidate(); }, onError,
  });
  const addEvidence = useMutation({
    mutationFn: (u: Upload) => api(`/cases/${caseId}/evidence`, {
      method: "POST",
      body: { title: u.filename.replace(/\.[^.]+$/, ""), document_id: u.id, evidence_type: u.document_class ?? "document",
              evidence_date: u.extraction?.fields.purchase_date?.value ?? null },
    }),
    onSuccess: invalidate, onError,
  });
  const removeUpload = useMutation({ mutationFn: (id: string) => api(`/cases/${caseId}/uploads/${id}`, { method: "DELETE" }), onSuccess: invalidate, onError });
  const removeEvidence = useMutation({ mutationFn: (id: string) => api(`/cases/${caseId}/evidence/${id}`, { method: "DELETE" }), onSuccess: invalidate, onError });

  const canUpload = !!user?.preferences.consent_document_storage;
  const evidenceDocIds = new Set(evidence.data?.map((e) => e.document_id));

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle>{t("documents.draftsTitle")}</CardTitle>
        </CardHeader>
        <CardBody>
          {!drafts.data?.length ? <p className="text-muted">{t("documents.noDrafts")}</p> : (
            <ul className="divide-y divide-line">
              {drafts.data.map((d) => (
                <li key={d.id} className="flex flex-wrap items-center gap-3 py-3">
                  <FileText className="size-5 text-navy-700" aria-hidden />
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold">{d.title}</p>
                    <p className="text-sm text-muted">{t("documents.version")} {d.current_version} · {formatDate(d.updated_at, lang)}</p>
                  </div>
                  <Badge tone={d.status === "approved" ? "success" : "neutral"}>{dict.documents.status[d.status]}</Badge>
                  {d.validation_status && (
                    <Badge tone={d.validation_status === "ok" ? "success" : d.validation_status === "blocked" ? "danger" : "warning"}>
                      {dict.documents.validation[d.validation_status]}
                    </Badge>
                  )}
                  <Button asChild size="sm"><Link href={`/cases/${caseId}/documents/${d.id}`}>{t("documents.review")}</Link></Button>
                  <Button size="sm" variant="ghost" onClick={() => download(`/cases/${caseId}/drafts/${d.id}/download?format=pdf`, `${d.doc_type}_${reference}.pdf`)}
                          aria-label={`${t("common.download")} PDF ${d.title}`}><Download aria-hidden />PDF</Button>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("documents.uploadsTitle")}</CardTitle>
          <input ref={fileRef} type="file" className="sr-only" id="upload-input" accept=".pdf,.docx,.jpg,.jpeg,.png"
                 onChange={(e) => onFile(e.target.files?.[0])} disabled={!canUpload} />
          <Button size="sm" onClick={() => fileRef.current?.click()} loading={uploading} disabled={!canUpload}>
            <FileUp aria-hidden /> {uploading ? t("documents.uploading") : t("common.upload")}
          </Button>
        </CardHeader>
        <CardBody className="space-y-3">
          <p className="text-sm text-muted">{t("documents.uploadHint")}</p>
          {!canUpload && <Alert tone="warning">{t("documents.consentNeeded")} <Link href="/settings" className="underline">{t("nav.settings")}</Link></Alert>}
          {!uploads.data?.length ? (
            <EmptyState icon={FileUp} title={t("documents.noUploads")} />
          ) : (
            <ul className="space-y-3">
              {uploads.data.map((u) => (
                <li key={u.id} className="rounded-lg border border-line p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="min-w-0 flex-1 truncate font-medium">{u.filename}</span>
                    {["uploaded", "processing"].includes(u.status) ? <Loader2 className="size-4 animate-spin text-muted" aria-label="processing" /> :
                      <Badge tone={u.status === "processed" ? "success" : u.status === "needs_ocr" ? "warning" : "danger"}>{u.status.replace("_", " ")}</Badge>}
                    {u.document_class && u.document_class !== "other" && <Badge tone="info">{u.document_class.replace("_", " ")}</Badge>}
                    <Button size="icon" variant="ghost" onClick={() => removeUpload.mutate(u.id)} aria-label={`${t("common.remove")} ${u.filename}`}><Trash2 /></Button>
                  </div>
                  {u.security_flags.includes("contains_ai_instructions") && (
                    <Alert tone="warning" className="mt-2"><ShieldAlert className="hidden" aria-hidden />{t("documents.injectionWarning")}</Alert>
                  )}
                  {u.status === "needs_ocr" && <Alert tone="info" className="mt-2">{t("documents.needsOcr")}</Alert>}
                  {u.extraction && Object.keys(u.extraction.fields).length > 0 && (
                    <div className="mt-2 space-y-1">
                      <p className="text-sm font-semibold">{t("documents.extracted")}</p>
                      <ul className="space-y-1 text-sm">
                        {Object.entries(u.extraction.fields).map(([key, f]) => (
                          <li key={key} className="flex flex-wrap items-center gap-2">
                            <span className="text-muted">{key.replace(/_/g, " ")}:</span>
                            <span className="font-medium">{f.value}</span>
                            {ACCEPTABLE.has(key) && (
                              <Button size="sm" variant="link" onClick={() => accept.mutate({ id: u.id, field: key })}>{t("documents.useField")}</Button>
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {u.status === "processed" && !evidenceDocIds.has(u.id) && (
                    <Button size="sm" variant="secondary" className="mt-2" onClick={() => addEvidence.mutate(u)}>
                      <ListPlus aria-hidden /> {t("documents.addEvidence")}
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader><CardTitle>{t("documents.evidenceTitle")}</CardTitle></CardHeader>
        <CardBody>
          {!evidence.data?.length ? <p className="text-muted">{t("documents.noEvidence")}</p> : (
            <ol className="space-y-2">
              {evidence.data.map((e) => (
                <li key={e.id} className="flex items-center gap-3 rounded-lg bg-canvas p-2">
                  <FileCheck2 className="size-5 text-success-700" aria-hidden />
                  <span className="font-semibold">{e.label}</span>
                  <span className="min-w-0 flex-1 truncate">{e.title}</span>
                  {e.evidence_date && <span className="text-sm text-muted">{formatDate(e.evidence_date, lang)}</span>}
                  <Button size="icon" variant="ghost" onClick={() => removeEvidence.mutate(e.id)} aria-label={`${t("common.remove")} ${e.label}`}><Trash2 /></Button>
                </li>
              ))}
            </ol>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
