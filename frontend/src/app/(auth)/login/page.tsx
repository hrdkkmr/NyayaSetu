"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { GoogleSignIn } from "@/components/google-sign-in";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardBody, Field, Input } from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { safeNext } from "@/lib/utils";

const schema = z.object({ email: z.string().email(), password: z.string().min(1) });
type Values = z.infer<typeof schema>;

function LoginForm() {
  const { t } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm<Values>({ resolver: zodResolver(schema) });

  const onSubmit = async (values: Values) => {
    setError(null);
    try {
      await api("/auth/login", { method: "POST", body: values });
      await qc.invalidateQueries({ queryKey: ["me"] });
      router.push(safeNext(params.get("next")));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("common.errorGeneric"));
    }
  };

  return (
    <Card>
      <CardBody className="space-y-5 py-6">
        <h1 className="text-2xl font-bold text-navy-900">{t("auth.loginTitle")}</h1>
        {error && <Alert tone="danger">{error}</Alert>}
        <GoogleSignIn next={safeNext(params.get("next"))} />
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <Field id="email" label={t("auth.email")} error={formState.errors.email && t("auth.email")}>
            <Input id="email" type="email" autoComplete="email" {...register("email")} aria-invalid={!!formState.errors.email} />
          </Field>
          <Field id="password" label={t("auth.password")}>
            <Input id="password" type="password" autoComplete="current-password" {...register("password")} />
          </Field>
          <Button type="submit" className="w-full" loading={formState.isSubmitting}>{t("common.signIn")}</Button>
        </form>
        <div className="flex flex-wrap justify-between gap-2 text-sm">
          <Link href="/forgot-password" className="text-navy-700 underline">{t("auth.forgot")}</Link>
          <span>{t("auth.noAccount")} <Link href="/register" className="font-semibold text-navy-700 underline">{t("common.register")}</Link></span>
        </div>
      </CardBody>
    </Card>
  );
}

export default function LoginPage() {
  return <Suspense><LoginForm /></Suspense>;
}
