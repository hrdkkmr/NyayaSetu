"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, FileText, MessageSquare, Pencil, Sparkles, UserCheck, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Badge, Card, CardBody, CardHeader, CardTitle, Input } from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { CaseDetail, Fact } from "@/lib/types";
import { formatDate, formatINR } from "@/lib/utils";

const TONE = { user_confirmed: "success", user_stated: "info", document_extracted: "accent", ai_inference: "warning" } as const;
const ICON = { user_confirmed: UserCheck, user_stated: MessageSquare, document_extracted: FileText, ai_inference: Sparkles };

function display(fact: Fact, lang: string) {
  if (fact.value_type === "date") return formatDate(fact.value, lang);
  if (fact.value_type === "money") return formatINR(fact.value);
  return fact.value;
}

export function FactsTab({ detail }: { detail: CaseDetail }) {
  const { t, lang, dict } = useI18n();
  const qc = useQueryClient();
  const [editing, setEditing] = useState<string | null>(null);
  const [value, setValue] = useState("");
  const caseId = detail.case.id;
  const invalidate = () => qc.invalidateQueries({ queryKey: ["case", caseId] });
  const onError = (e: unknown) => toast.error(e instanceof ApiError ? e.message : t("common.errorGeneric"));

  const act = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "confirm" | "reject" }) =>
      api(`/cases/${caseId}/facts/${id}/${action}`, { method: "POST" }),
    onSuccess: invalidate, onError,
  });
  const save = useMutation({
    mutationFn: ({ key, value }: { key: string; value: string }) => api(`/cases/${caseId}/facts`, { method: "POST", body: { key, value } }),
    onSuccess: () => { setEditing(null); invalidate(); toast.success(t("settings.saved")); }, onError,
  });

  const byKey = new Map<string, Fact[]>();
  detail.facts.forEach((f) => byKey.set(f.key, [...(byKey.get(f.key) ?? []), f]));

  return (
    <Card>
      <CardHeader><CardTitle>{t("case.tabs.facts")}</CardTitle></CardHeader>
      <CardBody className="space-y-1">
        <ul className="divide-y divide-line">
          {detail.fact_keys.map((k) => {
            const facts = byKey.get(k.key) ?? [];
            const label = lang === "hi" ? k.label_hi : k.label_en;
            const inputType = k.value_type === "date" ? "date" : k.value_type === "money" ? "number" : "text";
            return (
              <li key={k.key} className="py-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <p className="font-semibold text-navy-900">
                    {label} {k.required && <span className="text-xs font-normal text-muted">({t("common.required")})</span>}
                  </p>
                  {editing !== k.key && (
                    <Button size="sm" variant="ghost" onClick={() => { setEditing(k.key); setValue(facts[0]?.value ?? ""); }}>
                      <Pencil aria-hidden /> {facts.length ? t("case.editFact") : t("case.addValue")}
                    </Button>
                  )}
                </div>
                {editing === k.key && (
                  <form className="mt-2 flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); save.mutate({ key: k.key, value }); }}>
                    <label htmlFor={`fact-${k.key}`} className="sr-only">{label}</label>
                    <Input id={`fact-${k.key}`} type={inputType} value={value} onChange={(e) => setValue(e.target.value)} className="max-w-md flex-1" autoFocus />
                    <Button type="submit" size="sm" loading={save.isPending}>{t("common.save")}</Button>
                    <Button type="button" size="sm" variant="ghost" onClick={() => setEditing(null)}>{t("common.cancel")}</Button>
                  </form>
                )}
                {facts.length === 0 && editing !== k.key && <p className="text-sm text-muted">{t("common.unknown")}</p>}
                <ul className="mt-1 space-y-2">
                  {facts.map((f) => {
                    const Icon = ICON[f.provenance];
                    return (
                      <li key={f.id} className="rounded-lg bg-canvas p-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-medium">{display(f, lang)}</span>
                          <Badge tone={TONE[f.provenance]}><Icon className="size-3" aria-hidden />{dict.case.provenance[f.provenance]}</Badge>
                          {f.provenance === "ai_inference" && (
                            <span className="ml-auto flex gap-1">
                              <Button size="sm" variant="success" onClick={() => act.mutate({ id: f.id, action: "confirm" })}><Check aria-hidden />{t("case.confirmFact")}</Button>
                              <Button size="sm" variant="secondary" onClick={() => act.mutate({ id: f.id, action: "reject" })}><X aria-hidden />{t("case.rejectFact")}</Button>
                            </span>
                          )}
                        </div>
                        {f.excerpt && <p className="mt-1 text-xs text-muted">“{f.excerpt}”</p>}
                      </li>
                    );
                  })}
                </ul>
                {facts.length > 1 && new Set(facts.map((f) => f.value.toLowerCase())).size > 1 && (
                  <p className="mt-1 text-sm font-medium text-warning-700">⚠ Different sources disagree — confirm the correct value.</p>
                )}
              </li>
            );
          })}
        </ul>
      </CardBody>
    </Card>
  );
}
