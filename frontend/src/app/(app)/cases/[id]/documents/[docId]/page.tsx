"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, CheckCircle2, Download, Pencil, ShieldCheck, Undo2, XCircle } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Fragment, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Alert, Badge, Card, CardBody, CardHeader, CardTitle, Checkbox, Dialog, DialogContent, DialogTrigger, Label, Skeleton, Textarea,
} from "@/components/ui/primitives";
import { api, ApiError, download } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Block, GeneratedDoc } from "@/lib/types";
import { cn, formatDate } from "@/lib/utils";

function Highlighted({ text }: { text: string }) {
  const parts = text.split("[●]");
  return (
    <>
      {parts.map((p, i) => (
        <Fragment key={i}>
          {p}
          {i < parts.length - 1 && <mark className="rounded bg-warning-100 px-1 font-semibold text-warning-700">[●]</mark>}
        </Fragment>
      ))}
    </>
  );
}

function BlockView({ block, number }: { block: Block; number: number | null }) {
  switch (block.type) {
    case "notice":
      return <p className="rounded-lg bg-saffron-100/60 p-3 text-sm italic text-saffron-600">{block.text}</p>;
    case "heading":
      return <h2 className="text-center font-serif text-lg font-bold uppercase"><Highlighted text={block.text} /></h2>;
    case "subheading":
      return <h3 className="text-center font-serif font-bold underline"><Highlighted text={block.text} /></h3>;
    case "parties":
      return <div className="space-y-1 font-serif">{block.items.map((i) => <p key={i} className={i === "Versus" ? "text-center font-bold" : ""}><Highlighted text={i} /></p>)}</div>;
    case "numbered":
      return <p className="font-serif"><span className="font-bold">{number}. </span><Highlighted text={block.text} /></p>;
    case "list":
      return <ol className="list-[lower-alpha] space-y-1 pl-8 font-serif">{block.items.map((i) => <li key={i}><Highlighted text={i} /></li>)}</ol>;
    case "table":
      return (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse font-serif text-sm">
            <tbody>
              {block.rows.map((row, r) => (
                <tr key={r} className={r === 0 ? "bg-navy-50 font-semibold" : ""}>
                  {row.map((cell, c) => <td key={c} className="border border-line px-2 py-1"><Highlighted text={cell} /></td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    case "signature":
      return <div className="space-y-1 pt-4 font-serif">{block.items.map((i) => <p key={i}><Highlighted text={i} /></p>)}</div>;
    default:
      return <p className="font-serif"><Highlighted text={block.text} /></p>;
  }
}

export default function DocumentReviewPage() {
  const { id, docId } = useParams<{ id: string; docId: string }>();
  const { t, lang, dict } = useI18n();
  const qc = useQueryClient();
  const [editing, setEditing] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const [accept, setAccept] = useState(false);
  const [ackWarnings, setAckWarnings] = useState(false);
  const [open, setOpen] = useState(false);

  const { data: doc, isLoading } = useQuery({
    queryKey: ["draft", docId],
    queryFn: () => api<GeneratedDoc>(`/cases/${id}/drafts/${docId}`),
  });
  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["draft", docId] });
    void qc.invalidateQueries({ queryKey: ["drafts", id] });
    void qc.invalidateQueries({ queryKey: ["filing", id] });
  };
  const onError = (e: unknown) => toast.error(e instanceof ApiError ? e.message : t("common.errorGeneric"));

  const save = useMutation({
    mutationFn: ({ blockId, text }: { blockId: string; text: string }) =>
      api(`/cases/${id}/drafts/${docId}`, { method: "PUT", body: { edits: { [blockId]: text } } }),
    onSuccess: () => { setEditing(null); invalidate(); toast.success(t("settings.saved")); }, onError,
  });
  const approve = useMutation({
    mutationFn: () => {
      const current = doc!.versions!.find((v) => v.version_number === doc!.current_version)!;
      return api(`/cases/${id}/drafts/${docId}/approve`, {
        method: "POST",
        body: { version_number: current.version_number, content_sha256: current.content_sha256, statement_accepted: accept,
                acknowledge_warnings: ackWarnings },
      });
    },
    onSuccess: () => { setOpen(false); invalidate(); toast.success(dict.documents.status.approved); }, onError,
  });
  const revoke = useMutation({ mutationFn: () => api(`/cases/${id}/drafts/${docId}/revoke-approval`, { method: "POST" }), onSuccess: invalidate, onError });

  if (isLoading || !doc) return <Skeleton className="h-96" />;
  const current = doc.versions?.find((v) => v.version_number === doc.current_version);
  const blocks = current?.content?.blocks ?? [];
  const issues = current?.validation.issues ?? [];
  const status = current?.validation.status ?? "ok";
  const blockers = issues.filter((i) => i.severity === "blocker");
  let n = 0;

  return (
    <div className="space-y-4">
      <Link href={`/cases/${id}?tab=documents`} className="inline-flex items-center gap-1 text-navy-700 underline"><ArrowLeft className="size-4" aria-hidden />{t("common.back")}</Link>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-navy-900">{doc.title}</h1>
          <p className="text-sm text-muted">{t("documents.version")} {doc.current_version} · {doc.template}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={doc.status === "approved" ? "success" : "neutral"}>{dict.documents.status[doc.status]}</Badge>
          <Button size="sm" variant="secondary" onClick={() => download(`/cases/${id}/drafts/${docId}/download?format=pdf`, `${doc.doc_type}.pdf`)}><Download aria-hidden />{t("documents.pdf")}</Button>
          <Button size="sm" variant="secondary" onClick={() => download(`/cases/${id}/drafts/${docId}/download?format=docx`, `${doc.doc_type}.docx`)}><Download aria-hidden />{t("documents.docx")}</Button>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardBody className="space-y-4 bg-white py-6 md:px-10">
            {blocks.map((b) => {
              const number = b.type === "numbered" ? ++n : null;
              const hasIssue = issues.some((i) => i.blocks?.includes(b.id));
              return (
                <div key={b.id} className={cn("group relative rounded-md", hasIssue && "ring-2 ring-warning-100 ring-offset-4")}>
                  {editing === b.id ? (
                    <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); save.mutate({ blockId: b.id, text: editText }); }}>
                      <label htmlFor={`edit-${b.id}`} className="sr-only">{t("documents.editBlock")}</label>
                      <Textarea id={`edit-${b.id}`} rows={b.type === "list" ? 6 : 4} value={editText} onChange={(e) => setEditText(e.target.value)} autoFocus />
                      {b.type === "list" && <p className="text-xs text-muted">One item per line.</p>}
                      <div className="flex gap-2">
                        <Button type="submit" size="sm" loading={save.isPending}>{t("documents.saveEdit")}</Button>
                        <Button type="button" size="sm" variant="ghost" onClick={() => setEditing(null)}>{t("common.cancel")}</Button>
                      </div>
                    </form>
                  ) : (
                    <>
                      <BlockView block={b} number={number} />
                      {b.editable && (
                        <Button size="sm" variant="ghost" className="mt-1 opacity-70 group-hover:opacity-100"
                                onClick={() => { setEditing(b.id); setEditText(b.type === "list" ? b.items.join("\n") : b.text); }}>
                          <Pencil aria-hidden /> {t("documents.editBlock")}
                        </Button>
                      )}
                    </>
                  )}
                </div>
              );
            })}
          </CardBody>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader><CardTitle>{t("documents.issues")}</CardTitle><Badge tone={status === "ok" ? "success" : status === "blocked" ? "danger" : "warning"}>{dict.documents.validation[status]}</Badge></CardHeader>
            <CardBody>
              {issues.length === 0 ? <p className="flex items-center gap-2 text-success-700"><CheckCircle2 className="size-5" aria-hidden />{dict.documents.validation.ok}</p> : (
                <ul className="space-y-2">
                  {issues.map((i) => (
                    <li key={i.code + i.message_en} className="flex gap-2 text-sm">
                      {i.severity === "blocker" ? <XCircle className="mt-0.5 size-4 shrink-0 text-danger-700" aria-hidden /> : <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning-700" aria-hidden />}
                      {lang === "hi" ? i.message_hi : i.message_en}
                    </li>
                  ))}
                </ul>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader><CardTitle>{t("documents.approveTitle")}</CardTitle></CardHeader>
            <CardBody className="space-y-3">
              {doc.status === "approved" ? (
                <>
                  <Alert tone="success">{t("documents.approvedNote")}</Alert>
                  <Button variant="secondary" size="sm" onClick={() => revoke.mutate()}><Undo2 aria-hidden />{t("documents.revoke")}</Button>
                </>
              ) : (
                <Dialog open={open} onOpenChange={setOpen}>
                  <DialogTrigger asChild>
                    <Button className="w-full" disabled={blockers.length > 0}><ShieldCheck aria-hidden />{t("documents.approveButton")}</Button>
                  </DialogTrigger>
                  <DialogContent title={t("documents.approveTitle")} description={`${doc.title} — ${t("documents.version")} ${doc.current_version}`}>
                    <div className="space-y-4">
                      <p className="rounded-lg bg-canvas p-3">{doc.approval_statement}</p>
                      <div className="flex items-start gap-3">
                        <Checkbox id="approve-accept" checked={accept} onCheckedChange={(c) => setAccept(c === true)} />
                        <Label htmlFor="approve-accept" className="font-normal">{t("documents.approveButton")}</Label>
                      </div>
                      {status === "needs_attention" && (
                        <div className="flex items-start gap-3">
                          <Checkbox id="approve-warn" checked={ackWarnings} onCheckedChange={(c) => setAckWarnings(c === true)} />
                          <Label htmlFor="approve-warn" className="font-normal">{t("documents.acknowledgeWarnings")}</Label>
                        </div>
                      )}
                      <Button className="w-full" variant="success" disabled={!accept || (status === "needs_attention" && !ackWarnings)}
                              loading={approve.isPending} onClick={() => approve.mutate()}>{t("common.confirm")}</Button>
                    </div>
                  </DialogContent>
                </Dialog>
              )}
              {blockers.length > 0 && <p className="text-sm text-danger-700">{dict.documents.validation.blocked}</p>}
            </CardBody>
          </Card>

          <Card>
            <CardHeader><CardTitle>{t("documents.trace")}</CardTitle></CardHeader>
            <CardBody className="space-y-2 text-sm">
              <p><span className="font-semibold">{t("documents.factsUsed")}:</span> {current?.source_trace.fact_ids?.length ?? 0}</p>
              <p className="font-semibold">{t("documents.lawsUsed")}:</p>
              <ul className="list-disc pl-5">{(current?.source_trace.legal_refs ?? []).map((r) => <li key={r}>{r.split(":")[1]} ({r.split(":")[0]})</li>)}</ul>
            </CardBody>
          </Card>

          <Card>
            <CardHeader><CardTitle>{t("documents.versions")}</CardTitle></CardHeader>
            <CardBody>
              <ol className="space-y-2 text-sm">
                {[...(doc.versions ?? [])].reverse().map((v) => (
                  <li key={v.id} className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold">v{v.version_number}</span>
                    <span className="text-muted">{v.created_by === "user" ? t("chat.you") : "NyayaSetu"} · {formatDate(v.created_at, lang)}</span>
                    <Button size="sm" variant="link" onClick={() => download(`/cases/${id}/drafts/${docId}/download?format=pdf&version=${v.version_number}`, `${doc.doc_type}_v${v.version_number}.pdf`)}>PDF</Button>
                  </li>
                ))}
              </ol>
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}
