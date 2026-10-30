"use client";

import { AlertTriangle, BookOpen, CheckCircle2, ExternalLink, FileText, LifeBuoy, Phone } from "lucide-react";
import Link from "next/link";

import { SourceLink } from "@/components/case-bits";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/primitives";
import { useI18n } from "@/lib/i18n";
import type { Basis, Card } from "@/lib/types";

const CHOICES: Record<string, { value: string; en: string; hi: string }[]> = {
  purchase_mode: [
    { value: "online", en: "Online", hi: "ऑनलाइन" },
    { value: "in a shop", en: "In a shop", hi: "दुकान से" },
  ],
  desired_remedy: [
    { value: "replacement", en: "Replacement", hi: "सामान बदलना" },
    { value: "refund", en: "Refund", hi: "पैसे वापस" },
    { value: "repair", en: "Repair", hi: "मरम्मत" },
    { value: "compensation", en: "Compensation", hi: "मुआवज़ा" },
  ],
  commercial_purpose: [
    { value: "for my own personal use", en: "Personal / family use", hi: "निजी / परिवार के लिए" },
    { value: "for my business", en: "For business or resale", hi: "व्यापार या बेचने के लिए" },
  ],
};

export function MessageCards({
  cards, caseId, onReply, interactive,
}: { cards: Card[]; caseId: string; onReply: (text: string) => void; interactive: boolean }) {
  const { t, lang } = useI18n();
  return (
    <div className="mt-2 space-y-2">
      {cards.map((card, i) => {
        switch (card.type) {
          case "confirm_facts":
            return interactive ? (
              <div key={i} className="flex flex-wrap gap-2">
                <Button size="sm" variant="success" onClick={() => onReply(lang === "hi" ? "हाँ" : "yes")}>
                  <CheckCircle2 aria-hidden /> {t("chat.confirmAll")}
                </Button>
                <Button size="sm" variant="secondary" onClick={() => onReply(lang === "hi" ? "नहीं" : "no")}>{t("chat.notQuite")}</Button>
              </div>
            ) : null;
          case "question": {
            if (!interactive) return null;
            const slot = card.slot as string;
            if (card.confirm) {
              return (
                <div key={i} className="flex flex-wrap gap-2">
                  <Button size="sm" variant="success" onClick={() => onReply(lang === "hi" ? "हाँ" : "yes")}>{t("common.yes")}</Button>
                  <Button size="sm" variant="secondary" onClick={() => onReply(lang === "hi" ? "नहीं" : "no")}>{t("common.no")}</Button>
                </div>
              );
            }
            const options = CHOICES[slot];
            return (
              <div key={i} className="flex flex-wrap gap-2">
                {options?.map((o) => (
                  <Button key={o.value} size="sm" variant="secondary" onClick={() => onReply(o.value)}>
                    {lang === "hi" ? o.hi : o.en}
                  </Button>
                ))}
                <Button size="sm" variant="ghost" onClick={() => onReply(lang === "hi" ? "पता नहीं" : "skip")}>
                  {lang === "hi" ? "पता नहीं / आगे बढ़ें" : "Not sure / skip"}
                </Button>
              </div>
            );
          }
          case "rule_outcome":
            return (
              <div key={i} className="rounded-lg border border-line bg-white p-3 text-sm">
                <div className="flex items-start gap-2">
                  {card.grounded ? <BookOpen className="mt-0.5 size-4 shrink-0 text-navy-700" aria-hidden /> :
                    <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning-700" aria-hidden />}
                  <p>{card.text as string}</p>
                </div>
                <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 pl-6">
                  {(card.basis as Basis[]).map((b) => <SourceLink key={`${b.document_key}-${b.section_ref}`} basis={b} />)}
                </div>
              </div>
            );
          case "resources":
            return (
              <div key={i} className="rounded-lg border border-saffron-100 bg-saffron-100/40 p-3 text-sm">
                <p className="mb-2 flex items-center gap-2 font-semibold text-navy-900"><LifeBuoy className="size-4" aria-hidden />{t("chat.resources")}</p>
                <ul className="space-y-2">
                  {(card.items as { key: string; name: string; phone: string | null; url: string; use: string }[]).map((r) => (
                    <li key={r.key}>
                      <p className="font-medium">{r.name}</p>
                      <p className="text-muted">{r.use}</p>
                      <p className="flex flex-wrap gap-3">
                        {r.phone && <a href={`tel:${r.phone}`} className="inline-flex items-center gap-1 font-semibold text-navy-700 underline"><Phone className="size-3.5" aria-hidden />{r.phone}</a>}
                        <a href={r.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-navy-700 underline">{new URL(r.url).host}<ExternalLink className="size-3.5" aria-hidden /></a>
                      </p>
                    </li>
                  ))}
                </ul>
              </div>
            );
          case "sources":
            return (
              <div key={i} className="rounded-lg border border-line bg-white p-3 text-sm">
                <p className="mb-1 flex items-center gap-2 font-semibold"><BookOpen className="size-4" aria-hidden />{t("chat.sources")}
                  <Badge tone="neutral">{t("research.confidence")}: {(t(`research.confidenceLevels.${card.confidence as "high"}`))}</Badge></p>
                <ul className="space-y-1">
                  {(card.items as { chunk_id: string; citation: string; source_url: string }[]).slice(0, 3).map((r) => (
                    <li key={r.chunk_id}><a href={r.source_url} target="_blank" rel="noopener noreferrer" className="text-navy-700 underline">{r.citation}</a></li>
                  ))}
                </ul>
              </div>
            );
          case "missing_facts":
            return <p key={i} className="text-sm text-warning-700">{t("chat.missing")}: {(card.keys as string[]).join(", ")}</p>;
          case "documents":
          case "filing_ready":
            return (
              <Button key={i} asChild size="sm" variant="secondary">
                <Link href={`/cases/${caseId}?tab=${card.type === "documents" ? "documents" : "filing"}`}>
                  <FileText aria-hidden />{card.type === "documents" ? t("case.tabs.documents") : t("case.tabs.filing")}
                </Link>
              </Button>
            );
          default:
            return null;
        }
      })}
    </div>
  );
}
