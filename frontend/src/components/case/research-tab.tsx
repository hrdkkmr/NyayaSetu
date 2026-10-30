"use client";

import { useQuery } from "@tanstack/react-query";

import { LegalSourceCard } from "@/components/legal-source";
import { Alert, Card, CardBody, CardHeader, CardTitle, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Citation } from "@/lib/types";

export function ResearchTab({ caseId }: { caseId: string }) {
  const { t } = useI18n();
  const { data, isLoading } = useQuery({
    queryKey: ["research", caseId],
    queryFn: () => api<{ citations: Citation[]; limitations: string[] }>(`/cases/${caseId}/research`),
  });
  if (isLoading) return <Skeleton className="h-64" />;
  return (
    <div className="space-y-4">
      <Alert tone="info">{t("research.translationNote")}</Alert>
      {!data?.citations.length ? (
        <p className="text-muted">{t("case.missing")}</p>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {data.citations.map((c) => (
            <LegalSourceCard key={c.id} sectionRef={c.section_ref} text={c.text} explanation={c.explanation}
                             explanationMethod={c.explanation_generated_by} doc={c.document}
                             amendmentNotices={(c.document.amends ?? []).filter((a) => a.effect && a.provisions.some((p) => p.startsWith(c.section_ref)))
                               .map((a) => a.effect!)} />
          ))}
        </div>
      )}
      {data && (
        <Card>
          <CardHeader><CardTitle>{t("research.limitations")}</CardTitle></CardHeader>
          <CardBody><ul className="list-disc space-y-1 pl-5 text-sm">{data.limitations.map((l) => <li key={l}>{l}</li>)}</ul></CardBody>
        </Card>
      )}
    </div>
  );
}
