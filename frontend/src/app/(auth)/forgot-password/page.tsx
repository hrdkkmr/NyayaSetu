"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Alert, Card, CardBody, Field, Input } from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const RESEND_SECONDS = 30;
const PASSWORD_OK = (p: string) => p.length >= 10 && /[A-Za-z]/.test(p) && /\d/.test(p);

type ForgotResult = { message: string; dev_reset_code?: string };

export default function ForgotPasswordPage() {
  const { t } = useI18n();
  const [step, setStep] = useState<"email" | "code" | "done">("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [devCode, setDevCode] = useState<string | null>(null);
  const [cooldown, setCooldown] = useState(0);

  useEffect(() => {
    if (cooldown <= 0) return;
    const id = setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => clearTimeout(id);
  }, [cooldown]);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("common.errorGeneric"));
    } finally {
      setBusy(false);
    }
  };

  const sendCode = () =>
    run(async () => {
      const result = await api<ForgotResult>("/auth/password/forgot", { method: "POST", body: { email } });
      setDevCode(result.dev_reset_code ?? null);
      setCode("");
      setStep("code");
      setCooldown(RESEND_SECONDS);
    });

  const resetPassword = (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirm) {
      setError(t("auth.passwordMismatch"));
      return;
    }
    void run(async () => {
      await api("/auth/password/reset", { method: "POST", body: { email, code, new_password: password } });
      setStep("done");
    });
  };

  return (
    <Card>
      <CardBody className="space-y-5 py-6">
        <h1 className="text-2xl font-bold text-navy-900">
          {step === "code" ? t("auth.resetTitle") : t("auth.forgotTitle")}
        </h1>
        {error && <Alert tone="danger">{error}</Alert>}

        {step === "email" && (
          <form onSubmit={(e) => { e.preventDefault(); void sendCode(); }} className="space-y-4">
            <p className="text-muted">{t("auth.forgotBody")}</p>
            <Field id="email" label={t("auth.email")}>
              <Input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
            </Field>
            <Button type="submit" className="w-full" loading={busy}>{t("auth.sendCode")}</Button>
          </form>
        )}

        {step === "code" && (
          <form onSubmit={resetPassword} className="space-y-4">
            <Alert tone="success">{t("auth.codeSent", { email })}</Alert>
            {devCode && <Alert tone="warning" title={t("auth.devCode")}><span className="font-mono text-lg">{devCode}</span></Alert>}
            <Field id="code" label={t("auth.codeLabel")} hint={t("auth.codeHint")}>
              <Input
                id="code" required inputMode="numeric" autoComplete="one-time-code" pattern="\d{6}" maxLength={6}
                className="text-center font-mono text-2xl tracking-[0.5em]" aria-describedby="code-hint"
                value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
              />
            </Field>
            <Field id="password" label={t("auth.newPassword")} hint={t("auth.passwordHint")}>
              <Input id="password" type="password" minLength={10} required autoComplete="new-password" aria-describedby="password-hint"
                     value={password} onChange={(e) => setPassword(e.target.value)} />
            </Field>
            <Field id="confirm" label={t("auth.confirmPassword")}>
              <Input id="confirm" type="password" required autoComplete="new-password"
                     value={confirm} onChange={(e) => setConfirm(e.target.value)} />
            </Field>
            <Button type="submit" className="w-full" loading={busy} disabled={code.length !== 6 || !PASSWORD_OK(password)}>
              {t("auth.resetSubmit")}
            </Button>
            <div className="flex flex-wrap justify-between gap-2 text-sm">
              <Button type="button" variant="ghost" disabled={busy || cooldown > 0} onClick={() => void sendCode()}>
                {cooldown > 0 ? t("auth.resendIn", { seconds: cooldown }) : t("auth.resendCode")}
              </Button>
              <Button type="button" variant="ghost" onClick={() => { setStep("email"); setError(null); }}>
                {t("auth.changeEmail")}
              </Button>
            </div>
          </form>
        )}

        {step === "done" && (
          <>
            <Alert tone="success">{t("auth.resetDone")}</Alert>
            <Button asChild className="w-full"><Link href="/login">{t("common.signIn")}</Link></Button>
          </>
        )}

        {step !== "done" && <Link href="/login" className="text-sm text-navy-700 underline">{t("common.back")}</Link>}
      </CardBody>
    </Card>
  );
}
