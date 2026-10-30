"use client";

import { useQuery } from "@tanstack/react-query";
import { BookOpen, Search } from "lucide-react";
import { useState } from "react";

import { LegalSourceCard } from "@/components/legal-source";
import { Button } from "@/components/ui/button";
import { Alert, Badge, Card, CardBody, CardHeader, CardTitle, Input } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { LegalDoc, SearchResult } from "@/lib/types";
import { formatDate } from "@/lib/utils";

export default function ResearchPage() {
  const { t, lang, dict } = useI18n();
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const search = useQuery({
    queryKey: ["legal-search", query],
    queryFn: () => api<SearchResult>(`/legal/search?q=${encodeURIComponent(query)}`),
    enabled: query.length >= 2,
  });
  const sources = useQuery({ queryKey: ["legal-sources"], queryFn: () => api<LegalDoc[]>("/legal/sources") });
  const result = search.data;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-navy-900 md:text-3xl">{t("research.title")}</h1>
        <p className="text-muted">{t("research.body")}</p>
      </div>
      <form role="search" onSubmit={(e) => { e.preventDefault(); setQuery(q.trim()); }} className="flex gap-2">
        <label htmlFor="legal-q" className="sr-only">{t("research.search")}</label>
        <Input id="legal-q" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("research.placeholder")} className="flex-1" />
        <Button type="submit" loading={search.isFetching}><Search aria-hidden />{t("research.search")}</Button>
      </form>
      <Alert tone="info">{t("research.translationNote")}</Alert>

      {result && (
        <section className="space-y-3" aria-live="polite">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <Badge tone={result.confidence === "high" ? "success" : result.confidence === "medium" ? "info" : "warning"}>
              {t("research.confidence")}: {dict.research.confidenceLevels[result.confidence]}
            </Badge>
            {result.notes.map((n) => <span key={n} className="text-muted">{n}</span>)}
          </div>
          {result.confidence === "none" || result.confidence === "low" ? <Alert tone="warning">{t("research.noResults")}</Alert> : null}
          <div className="grid gap-4 lg:grid-cols-2">
            {result.results.map((r) => (
              <LegalSourceCard key={r.chunk_id} sectionRef={r.section_ref} text={r.text} amendmentNotices={r.amendment_notices}
                               doc={{ title: r.document_title, source_url: r.source_url, source_name: r.source_name,
                                      publication_date: r.publication_date, effective_date_note: r.effective_date_note,
                                      version_label: r.version_label, verification_status: r.verification_status,
                                      retrieved_at: r.retrieved_at }} />
            ))}
          </div>
        </section>
      )}

      <Card>
        <CardHeader><CardTitle>{t("research.sourcesTitle")}</CardTitle></CardHeader>
        <CardBody>
          <ul className="divide-y divide-line">
            {sources.data?.map((d) => (
              <li key={d.key} className="py-3">
                <p className="flex items-start gap-2 font-semibold text-navy-900"><BookOpen className="mt-1 size-4 shrink-0" aria-hidden />{d.title}</p>
                <p className="text-sm text-muted">
                  {d.source_name} · {t("research.published")} {formatDate(d.publication_date, lang)} · {d.chunk_count} provisions
                </p>
                <p className="text-sm">{(dict.research.verificationStates as Record<string, string>)[d.verification_status]}</p>
                <a href={d.source_url} target="_blank" rel="noopener noreferrer" className="text-sm text-navy-700 underline">{t("research.open")}</a>
              </li>
            ))}
          </ul>
        </CardBody>
      </Card>
    </div>
  );
}
