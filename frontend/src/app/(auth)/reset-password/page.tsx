"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Button } from "@/components/ui/button";
import { Alert, Card, CardBody, Field, Input } from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

function ResetForm() {
  const { t } = useI18n();
  const token = useSearchParams().get("token") ?? "";
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/auth/password/reset", { method: "POST", body: { token, new_password: password } });
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("common.errorGeneric"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardBody className="space-y-5 py-6">
        <h1 className="text-2xl font-bold text-navy-900">{t("auth.resetTitle")}</h1>
        {error && <Alert tone="danger">{error}</Alert>}
        {done ? (
          <>
            <Alert tone="success">{t("auth.resetDone")}</Alert>
            <Button asChild className="w-full"><Link href="/login">{t("common.signIn")}</Link></Button>
          </>
        ) : (
          <form onSubmit={submit} className="space-y-4">
            <Field id="password" label={t("auth.newPassword")} hint={t("auth.passwordHint")}>
              <Input id="password" type="password" minLength={10} required autoComplete="new-password"
                     value={password} onChange={(e) => setPassword(e.target.value)} />
            </Field>
            <Button type="submit" className="w-full" loading={busy} disabled={!token}>{t("common.save")}</Button>
          </form>
        )}
      </CardBody>
    </Card>
  );
}

export default function ResetPasswordPage() {
  return <Suspense><ResetForm /></Suspense>;
}
