"use client";

import { Keyboard, Lock, Mic } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardBody, Field, Textarea } from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { CaseSummary, TurnResult } from "@/lib/types";
import { cn } from "@/lib/utils";

function NewCase() {
  const { t, lang } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const [mode, setMode] = useState<"voice" | "text">(params.get("mode") === "text" ? "text" : "voice");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);

  const start = async () => {
    setBusy(true);
    try {
      const body = mode === "text" ? { language: lang, description, modality: "text" } : { language: lang };
      const res = await api<{ case: CaseSummary; turn?: TurnResult }>("/cases", { method: "POST", body });
      if (res.turn) {
        try {
          sessionStorage.setItem(`ns-turn-${res.case.id}`, JSON.stringify(res.turn));
        } catch {
          /* storage unavailable */
        }
      }
      router.push(`/cases/${res.case.id}?tab=conversation&mode=${mode}`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t("common.errorGeneric"));
      setBusy(false);
    }
  };

  const option = (value: "voice" | "text", Icon: typeof Mic, title: string, body: string) => (
    <button
      type="button"
      onClick={() => setMode(value)}
      aria-pressed={mode === value}
      className={cn(
        "flex w-full items-start gap-4 rounded-xl border-2 bg-white p-5 text-left transition-colors",
        mode === value ? "border-navy-700 bg-navy-50" : "border-line hover:border-navy-600",
      )}
    >
      <span className={cn("flex size-12 shrink-0 items-center justify-center rounded-full", mode === value ? "bg-navy-800 text-white" : "bg-navy-100 text-navy-800")}>
        <Icon className="size-6" aria-hidden />
      </span>
      <span>
        <span className="block text-lg font-semibold text-navy-900">{title}</span>
        <span className="block text-muted">{body}</span>
      </span>
    </button>
  );

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-navy-900 md:text-3xl">{t("newCase.title")}</h1>
        <p className="text-muted">{t("newCase.body")}</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {option("voice", Mic, t("newCase.voiceTitle"), t("newCase.voiceBody"))}
        {option("text", Keyboard, t("newCase.textTitle"), t("newCase.textBody"))}
      </div>
      <Card>
        <CardBody className="space-y-4">
          {mode === "text" && (
            <Field id="description" label={t("newCase.describeLabel")}>
              <Textarea id="description" rows={6} maxLength={4000} value={description}
                        onChange={(e) => setDescription(e.target.value)} placeholder={t("newCase.describePlaceholder")} />
            </Field>
          )}
          <Button size="lg" className="w-full" loading={busy} disabled={mode === "text" && description.trim().length < 10} onClick={start}>
            {mode === "voice" ? <Mic aria-hidden /> : <Keyboard aria-hidden />} {t("newCase.start")}
          </Button>
          <p className="flex items-center gap-2 text-sm text-muted"><Lock className="size-4" aria-hidden />{t("newCase.privacyNote")}</p>
        </CardBody>
      </Card>
      <p className="text-sm text-muted">{t("common.notAdvice")}</p>
    </div>
  );
}

export default function NewCasePage() {
  return <Suspense><NewCase /></Suspense>;
}
