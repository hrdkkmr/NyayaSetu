"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { GoogleSignIn } from "@/components/google-sign-in";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardBody, Checkbox, Field, Input, Label, Select } from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const schema = z.object({
  full_name: z.string().min(2).max(200),
  email: z.string().email(),
  phone: z.string().regex(/^(\+?\d[\d\s-]{8,14})?$/).optional(),
  password: z.string().min(10).regex(/[A-Za-z]/).regex(/\d/),
  language: z.enum(["en", "hi"]),
  accept_terms: z.literal(true),
  consent_store_transcripts: z.boolean(),
  consent_document_storage: z.boolean(),
  consent_external_ai: z.boolean(),
});
type Values = z.infer<typeof schema>;

export default function RegisterPage() {
  const { t, lang } = useI18n();
  const router = useRouter();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, control, formState } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      language: lang, consent_store_transcripts: true, consent_document_storage: true, consent_external_ai: false,
    } as Partial<Values>,
  });
  const err = formState.errors;

  const onSubmit = async (v: Values) => {
    setError(null);
    try {
      await api("/auth/register", {
        method: "POST",
        body: { full_name: v.full_name, email: v.email, phone: v.phone || null, password: v.password,
                language: v.language, accept_terms: v.accept_terms },
      });
      await api("/users/me/preferences", {
        method: "PATCH",
        body: { consent_store_transcripts: v.consent_store_transcripts, consent_document_storage: v.consent_document_storage,
                consent_external_ai: v.consent_external_ai },
      });
      await qc.invalidateQueries({ queryKey: ["me"] });
      router.push("/cases/new");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("common.errorGeneric"));
    }
  };

  const consent = (name: "consent_store_transcripts" | "consent_document_storage" | "consent_external_ai", label: string) => (
    <Controller
      control={control}
      name={name}
      render={({ field }) => (
        <div className="flex items-start gap-3">
          <Checkbox id={name} checked={field.value} onCheckedChange={(c) => field.onChange(c === true)} />
          <Label htmlFor={name} className="font-normal">{label}</Label>
        </div>
      )}
    />
  );

  return (
    <Card>
      <CardBody className="space-y-5 py-6">
        <h1 className="text-2xl font-bold text-navy-900">{t("auth.registerTitle")}</h1>
        {error && <Alert tone="danger">{error}</Alert>}
        <GoogleSignIn next="/cases/new" />
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <Field id="full_name" label={t("auth.fullName")} error={err.full_name && t("auth.fullName")}>
            <Input id="full_name" autoComplete="name" {...register("full_name")} aria-invalid={!!err.full_name} />
          </Field>
          <Field id="email" label={t("auth.email")} error={err.email && t("auth.email")}>
            <Input id="email" type="email" autoComplete="email" {...register("email")} aria-invalid={!!err.email} />
          </Field>
          <Field id="phone" label={<>{t("auth.phone")} <span className="font-normal text-muted">({t("common.optional")})</span></>}
                 error={err.phone && t("auth.phone")}>
            <Input id="phone" type="tel" inputMode="tel" autoComplete="tel" {...register("phone")} />
          </Field>
          <Field id="password" label={t("auth.password")} hint={t("auth.passwordHint")} error={err.password && t("auth.passwordHint")}>
            <Input id="password" type="password" autoComplete="new-password" {...register("password")} aria-invalid={!!err.password}
                   aria-describedby="password-hint" />
          </Field>
          <Field id="language" label={t("auth.preferredLanguage")}>
            <Select id="language" {...register("language")}>
              <option value="hi">हिन्दी</option>
              <option value="en">English</option>
            </Select>
          </Field>
          <fieldset className="space-y-3 rounded-lg border border-line p-3">
            <legend className="px-1 text-sm font-semibold">{t("auth.consentsTitle")}</legend>
            {consent("consent_store_transcripts", t("auth.consentTranscripts"))}
            {consent("consent_document_storage", t("auth.consentDocuments"))}
            {consent("consent_external_ai", t("auth.consentAi"))}
          </fieldset>
          <Controller
            control={control}
            name="accept_terms"
            render={({ field }) => (
              <div className="flex items-start gap-3">
                <Checkbox id="accept_terms" checked={field.value === true} onCheckedChange={(c) => field.onChange(c === true)}
                          aria-invalid={!!err.accept_terms} />
                <Label htmlFor="accept_terms" className="font-normal">
                  {t("auth.acceptTerms")} <Link href="/privacy" className="text-navy-700 underline">Privacy</Link>
                </Label>
              </div>
            )}
          />
          {err.accept_terms && <p role="alert" className="text-sm font-medium text-danger-700">{t("auth.acceptTerms")}</p>}
          <Button type="submit" className="w-full" loading={formState.isSubmitting}>{t("common.register")}</Button>
        </form>
        <p className="text-sm">{t("auth.haveAccount")} <Link href="/login" className="font-semibold text-navy-700 underline">{t("common.signIn")}</Link></p>
      </CardBody>
    </Card>
  );
}
