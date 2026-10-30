"use client";

import { ChevronDown, ExternalLink, History, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { shortTitle } from "@/components/case-bits";
import { Badge } from "@/components/ui/primitives";
import { useI18n } from "@/lib/i18n";
import { formatDate } from "@/lib/utils";

interface Props {
  sectionRef: string | null;
  text: string;
  explanation?: string | null;
  explanationMethod?: string;
  doc: {
    title: string;
    source_url: string;
    source_name?: string | null;
    publication_date: string | null;
    effective_date_note?: string | null;
    version_label?: string | null;
    verification_status: string;
    retrieved_at: string | null;
  };
  amendmentNotices?: string[];
}

export function LegalSourceCard({ sectionRef, text, explanation, explanationMethod, doc, amendmentNotices = [] }: Props) {
  const { t, lang, dict } = useI18n();
  const [open, setOpen] = useState(false);
  const verified = doc.verification_status === "verified_by_reviewer";
  return (
    <article className="rounded-xl border border-line bg-white p-4">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold text-navy-900">{sectionRef} — {shortTitle(doc.title)}</h3>
          <p className="text-xs text-muted">{doc.source_name}</p>
        </div>
        <a href={doc.source_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-sm font-medium text-navy-700 underline">
          {t("research.open")} <ExternalLink className="size-3.5" aria-hidden />
        </a>
      </header>
      {explanation && (
        <div className="mt-3 rounded-lg bg-navy-50 p-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-navy-700">{t("research.explanation")}</p>
          <p className="mt-1">{explanation}</p>
          {explanationMethod === "llm_from_source_text" && <p className="mt-1 text-xs text-muted">AI-generated from the provision text</p>}
        </div>
      )}
      {amendmentNotices.map((n) => (
        <p key={n} className="mt-2 flex gap-2 rounded-lg bg-warning-100 p-2 text-sm text-warning-700">
          <History className="mt-0.5 size-4 shrink-0" aria-hidden /><span><strong>{t("research.amendment")}:</strong> {n}</span>
        </p>
      ))}
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
              className="mt-3 flex items-center gap-1 text-sm font-semibold text-navy-800">
        <ChevronDown className={`size-4 transition-transform ${open ? "rotate-180" : ""}`} aria-hidden /> {t("research.originalText")}
      </button>
      {open && <blockquote lang="en" className="mt-2 whitespace-pre-wrap border-l-4 border-navy-100 pl-3 text-sm">{text}</blockquote>}
      <dl className="mt-3 grid gap-x-4 gap-y-1 text-xs text-muted sm:grid-cols-2">
        <div><dt className="inline font-semibold">{t("research.published")}: </dt><dd className="inline">{formatDate(doc.publication_date, lang)}</dd></div>
        <div><dt className="inline font-semibold">{t("research.retrieved")}: </dt><dd className="inline">{formatDate(doc.retrieved_at, lang)}</dd></div>
        {doc.version_label && <div className="sm:col-span-2"><dt className="inline font-semibold">{t("research.version")}: </dt><dd className="inline">{doc.version_label}</dd></div>}
        {doc.effective_date_note && <div className="sm:col-span-2"><dt className="inline font-semibold">{t("research.effective")}: </dt><dd className="inline">{doc.effective_date_note}</dd></div>}
      </dl>
      <Badge tone={verified ? "success" : doc.verification_status === "stale" ? "danger" : "neutral"} className="mt-2">
        <ShieldCheck className="size-3" aria-hidden />
        {(dict.research.verificationStates as Record<string, string>)[doc.verification_status] ?? doc.verification_status}
      </Badge>
    </article>
  );
}
