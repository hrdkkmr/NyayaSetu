"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Laptop, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Alert, Card, CardBody, CardHeader, CardTitle, Field, Input, Label, Select, Switch } from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import type { Preferences } from "@/lib/types";
import { formatDate } from "@/lib/utils";

interface SessionRow { id: string; user_agent: string | null; last_used_at: string; current: boolean }

export default function SettingsPage() {
  const { t, lang } = useI18n();
  const { user, refresh } = useAuth();
  const qc = useQueryClient();
  const [name, setName] = useState(user?.full_name ?? "");
  const [phone, setPhone] = useState(user?.phone ?? "");
  const [pw, setPw] = useState({ current: "", next: "" });
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: () => api<SessionRow[]>("/users/me/sessions") });
  const voice = useQuery({ queryKey: ["voice-config"], queryFn: () => api<{ providers: { sarvam: { available: boolean } } }>("/voice/config") });
  const onError = (e: unknown) => toast.error(e instanceof ApiError ? e.message : t("common.errorGeneric"));
  const ok = () => { toast.success(t("settings.saved")); void refresh(); };

  const setPref = useMutation({
    mutationFn: (patch: Partial<Preferences>) => api("/users/me/preferences", { method: "PATCH", body: patch }),
    onSuccess: ok, onError,
  });
  const saveProfile = useMutation({
    mutationFn: () => api("/users/me", { method: "PATCH", body: { full_name: name, phone: phone || "" } }), onSuccess: ok, onError,
  });
  const changePw = useMutation({
    mutationFn: () => api("/users/me/password", { method: "POST", body: { current_password: pw.current, new_password: pw.next } }),
    onSuccess: () => { setPw({ current: "", next: "" }); ok(); }, onError,
  });
  const revoke = useMutation({
    mutationFn: (id: string) => api(`/users/me/sessions/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }),
  });
  const deletion = useMutation({
    mutationFn: (request: boolean) => api("/users/me/deletion-request", { method: request ? "POST" : "DELETE" }),
    onSuccess: ok, onError,
  });

  const exportData = async () => {
    const data = await api("/users/me/export");
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "nyayasetu-my-data.json";
    a.click();
  };

  if (!user) return null;
  const p = user.preferences;
  const toggle = (key: keyof Preferences, label: string) => (
    <div className="flex items-center justify-between gap-4 py-2">
      <Label htmlFor={key} className="font-normal">{label}</Label>
      <Switch id={key} checked={Boolean(p[key])} onCheckedChange={(v) => setPref.mutate({ [key]: v })} />
    </div>
  );

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <h1 className="text-2xl font-bold text-navy-900 md:text-3xl">{t("settings.title")}</h1>

      <Card>
        <CardHeader><CardTitle>{t("settings.profile")}</CardTitle></CardHeader>
        <CardBody>
          <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); saveProfile.mutate(); }}>
            <Field id="name" label={t("auth.fullName")}><Input id="name" value={name} onChange={(e) => setName(e.target.value)} /></Field>
            <Field id="phone" label={t("auth.phone")}><Input id="phone" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} /></Field>
            <p className="text-sm text-muted sm:col-span-2">{t("auth.email")}: {user.email}</p>
            <Button type="submit" loading={saveProfile.isPending} className="sm:w-fit">{t("common.save")}</Button>
          </form>
        </CardBody>
      </Card>

      <Card>
        <CardHeader><CardTitle>{t("settings.language")}</CardTitle></CardHeader>
        <CardBody className="space-y-3">
          <Field id="lang" label={t("common.language")}>
            <Select id="lang" value={p.language} onChange={(e) => setPref.mutate({ language: e.target.value as "en" | "hi" })}>
              <option value="hi">हिन्दी</option><option value="en">English</option>
            </Select>
          </Field>
          <Field id="scale" label={`${t("settings.textSize")} (${Math.round(p.text_scale * 100)}%)`}>
            <input id="scale" type="range" min={0.9} max={1.5} step={0.05} defaultValue={p.text_scale} className="w-full accent-navy-700"
                   onMouseUp={(e) => setPref.mutate({ text_scale: Number((e.target as HTMLInputElement).value) })}
                   onKeyUp={(e) => setPref.mutate({ text_scale: Number((e.target as HTMLInputElement).value) })} />
          </Field>
          {toggle("high_contrast", t("settings.highContrast"))}
          {toggle("reduce_motion", t("settings.reduceMotion"))}
        </CardBody>
      </Card>

      <Card>
        <CardHeader><CardTitle>{t("settings.voice")}</CardTitle></CardHeader>
        <CardBody className="space-y-3">
          <Field id="vp" label={t("settings.voiceProvider")}>
            <Select id="vp" value={p.voice_provider} onChange={(e) => setPref.mutate({ voice_provider: e.target.value as "browser" | "sarvam" })}>
              <option value="browser">{t("voice.providerBrowser")}</option>
              <option value="sarvam" disabled={!voice.data?.providers.sarvam.available}>
                {t("voice.providerServer")}{!voice.data?.providers.sarvam.available ? " — not configured" : ""}
              </option>
            </Select>
          </Field>
          <Field id="rate" label={`${t("settings.speechRate")} (${p.speech_rate.toFixed(2)}×)`}>
            <input id="rate" type="range" min={0.7} max={1.3} step={0.05} defaultValue={p.speech_rate} className="w-full accent-navy-700"
                   onMouseUp={(e) => setPref.mutate({ speech_rate: Number((e.target as HTMLInputElement).value) })}
                   onKeyUp={(e) => setPref.mutate({ speech_rate: Number((e.target as HTMLInputElement).value) })} />
          </Field>
          {toggle("autoplay_voice", t("settings.autoplay"))}
        </CardBody>
      </Card>

      <Card>
        <CardHeader><CardTitle>{t("settings.privacy")}</CardTitle></CardHeader>
        <CardBody>
          {toggle("consent_store_transcripts", t("settings.consentTranscripts"))}
          {toggle("consent_document_storage", t("settings.consentDocs"))}
          {toggle("consent_store_audio", t("settings.consentAudio"))}
          {toggle("consent_external_ai", t("settings.consentAi"))}
          {p.consents_updated_at && <p className="text-sm text-muted">{t("settings.consentsUpdated")}: {formatDate(p.consents_updated_at, lang)}</p>}
        </CardBody>
      </Card>

      <Card>
        <CardHeader><CardTitle>{t("settings.password")}</CardTitle></CardHeader>
        <CardBody>
          <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); changePw.mutate(); }}>
            <Field id="cur" label={t("settings.currentPassword")}><Input id="cur" type="password" autoComplete="current-password" value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} /></Field>
            <Field id="new" label={t("auth.newPassword")} hint={t("auth.passwordHint")}><Input id="new" type="password" autoComplete="new-password" value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} /></Field>
            <Button type="submit" loading={changePw.isPending} disabled={!pw.current || pw.next.length < 10} className="sm:w-fit">{t("common.save")}</Button>
          </form>
        </CardBody>
      </Card>

      <Card>
        <CardHeader><CardTitle>{t("settings.sessions")}</CardTitle></CardHeader>
        <CardBody>
          <ul className="divide-y divide-line">
            {sessions.data?.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center gap-3 py-2">
                <Laptop className="size-5 text-muted" aria-hidden />
                <span className="min-w-0 flex-1 truncate text-sm">{s.user_agent ?? "Unknown device"}</span>
                <span className="text-sm text-muted">{formatDate(s.last_used_at, lang)}</span>
                {s.current ? <span className="text-sm font-semibold">{t("settings.thisDevice")}</span> :
                  <Button size="sm" variant="secondary" onClick={() => revoke.mutate(s.id)}>{t("settings.signOutDevice")}</Button>}
              </li>
            ))}
          </ul>
        </CardBody>
      </Card>

      <Card>
        <CardHeader><CardTitle>{t("settings.data")}</CardTitle></CardHeader>
        <CardBody className="space-y-4">
          <Button variant="secondary" onClick={exportData}><Download aria-hidden />{t("settings.export")}</Button>
          <div className="space-y-2 rounded-lg border border-danger-100 p-3">
            <p className="font-semibold text-danger-700">{t("settings.deleteTitle")}</p>
            <p className="text-sm">{t("settings.deleteBody")}</p>
            {user.deletion_requested_at ? (
              <>
                <Alert tone="warning">{t("settings.deleteRequested", { date: formatDate(user.deletion_requested_at, lang) })}</Alert>
                <Button variant="secondary" onClick={() => deletion.mutate(false)}>{t("settings.deleteCancel")}</Button>
              </>
            ) : (
              <Button variant="danger" onClick={() => deletion.mutate(true)}><Trash2 aria-hidden />{t("settings.deleteRequest")}</Button>
            )}
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
