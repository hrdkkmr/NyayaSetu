"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { createContext, useContext, useEffect, type ReactNode } from "react";

import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { User } from "@/lib/types";

interface AuthValue {
  user: User | null;
  loading: boolean;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const router = useRouter();
  const { setLang } = useI18n();
  const { data, isLoading } = useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        return await api<User>("/auth/me");
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    staleTime: 60_000,
    retry: false,
  });

  // Apply accessibility preferences to the document.
  useEffect(() => {
    const prefs = data?.preferences;
    const root = document.documentElement;
    if (!prefs) return;
    root.style.setProperty("--text-scale", String(prefs.text_scale));
    root.dataset.contrast = prefs.high_contrast ? "high" : "normal";
    root.dataset.reduceMotion = String(prefs.reduce_motion);
    setLang(prefs.language);
  }, [data?.preferences, setLang]);

  const value: AuthValue = {
    user: data ?? null,
    loading: isLoading,
    refresh: async () => {
      await qc.invalidateQueries({ queryKey: ["me"] });
    },
    logout: async () => {
      try {
        await api("/auth/logout", { method: "POST" });
      } catch {
        /* already signed out */
      }
      qc.clear();
      router.push("/login");
    },
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
