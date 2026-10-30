"use client";

import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Alert, Card, CardBody, Field, Input } from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export default function ForgotPasswordPage() {
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ message: string; dev_reset_token?: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setResult(await api("/auth/password/forgot", { method: "POST", body: { email } }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("common.errorGeneric"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardBody className="space-y-5 py-6">
        <h1 className="text-2xl font-bold text-navy-900">{t("auth.forgotTitle")}</h1>
        <p className="text-muted">{t("auth.forgotBody")}</p>
        {error && <Alert tone="danger">{error}</Alert>}
        {result ? (
          <div className="space-y-3">
            <Alert tone="success">{result.message}</Alert>
            {result.dev_reset_token && (
              <Alert tone="warning" title={t("auth.devToken")}>
                <Link className="break-all underline" href={`/reset-password?token=${encodeURIComponent(result.dev_reset_token)}`}>
                  /reset-password
                </Link>
              </Alert>
            )}
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-4">
            <Field id="email" label={t("auth.email")}>
              <Input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
            </Field>
            <Button type="submit" className="w-full" loading={busy}>{t("auth.sendLink")}</Button>
          </form>
        )}
        <Link href="/login" className="text-sm text-navy-700 underline">{t("common.back")}</Link>
      </CardBody>
    </Card>
  );
}
