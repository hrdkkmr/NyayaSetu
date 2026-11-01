"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Alert } from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

/** Minimal typing for the parts of Google Identity Services we use. */
interface GoogleAccountsId {
  initialize(config: { client_id: string; callback: (r: { credential: string }) => void; ux_mode?: "popup" }): void;
  renderButton(el: HTMLElement, options: Record<string, string | number>): void;
}
declare global {
  interface Window {
    google?: { accounts: { id: GoogleAccountsId } };
  }
}

const GSI_SRC = "https://accounts.google.com/gsi/client";
let gsiLoading: Promise<void> | null = null;

function loadGsi(): Promise<void> {
  if (window.google?.accounts?.id) return Promise.resolve();
  gsiLoading ??= new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = GSI_SRC;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => {
      gsiLoading = null;
      reject(new Error("gsi_load_failed"));
    };
    document.head.appendChild(script);
  });
  return gsiLoading;
}

/**
 * "Continue with Google". Renders nothing unless the backend reports a Google client ID,
 * so the page works unchanged when Google sign-in is not configured.
 */
export function GoogleSignIn({ next }: { next: string }) {
  const { t, lang } = useI18n();
  const router = useRouter();
  const qc = useQueryClient();
  const holder = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const { data } = useQuery({
    queryKey: ["auth-providers"],
    queryFn: () => api<{ google_client_id: string | null }>("/auth/providers"),
    staleTime: Infinity,
  });
  const clientId = data?.google_client_id;

  useEffect(() => {
    if (!clientId) return;
    let cancelled = false;
    loadGsi()
      .then(() => {
        const el = holder.current;
        const gsi = window.google?.accounts.id;
        if (cancelled || !el || !gsi) return;
        gsi.initialize({
          client_id: clientId,
          ux_mode: "popup",
          callback: async ({ credential }) => {
            setError(null);
            try {
              await api("/auth/google", { method: "POST", body: { credential, language: lang } });
              await qc.invalidateQueries({ queryKey: ["me"] });
              router.push(next);
            } catch (e) {
              setError(e instanceof ApiError ? e.message : t("auth.googleError"));
            }
          },
        });
        el.replaceChildren();
        gsi.renderButton(el, {
          type: "standard", theme: "outline", size: "large", text: "continue_with", shape: "pill",
          width: Math.min(el.clientWidth || 320, 400), locale: lang === "hi" ? "hi" : "en",
        });
      })
      .catch(() => !cancelled && setError(t("auth.googleError")));
    return () => {
      cancelled = true;
    };
  }, [clientId, lang, next, qc, router, t]);

  if (!clientId) return null;
  return (
    <div className="space-y-3">
      {error && <Alert tone="danger">{error}</Alert>}
      <div ref={holder} className="flex min-h-[44px] justify-center" aria-label={t("auth.continueWithGoogle")} />
      <p className="text-center text-xs text-muted">{t("auth.googleTerms")}</p>
      <div className="flex items-center gap-3 text-sm text-muted" aria-hidden="true">
        <span className="h-px flex-1 bg-line" />
        {t("auth.or")}
        <span className="h-px flex-1 bg-line" />
      </div>
    </div>
  );
}
