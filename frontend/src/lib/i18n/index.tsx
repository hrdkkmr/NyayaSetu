"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import type { Lang } from "@/lib/types";
import en, { type Dictionary } from "./en";
import hi from "./hi";

const DICTIONARIES: Record<Lang, Dictionary> = { en, hi };
const STORAGE_KEY = "ns-lang";

type Path<T, P extends string = ""> = {
  [K in keyof T & string]: T[K] extends string ? `${P}${K}` : Path<T[K], `${P}${K}.`>;
}[keyof T & string];

export type TKey = Path<Dictionary>;

interface I18nValue {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: (key: TKey, vars?: Record<string, string | number>) => string;
  dict: Dictionary;
}

const I18nContext = createContext<I18nValue | null>(null);

function lookup(dict: Dictionary, key: string): string {
  const value = key.split(".").reduce<unknown>((acc, part) => (acc as Record<string, unknown>)?.[part], dict);
  return typeof value === "string" ? value : key;
}

export function I18nProvider({ children, initial = "en" }: { children: ReactNode; initial?: Lang }) {
  const [lang, setLangState] = useState<Lang>(initial);

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(STORAGE_KEY);
      if (saved === "en" || saved === "hi") setLangState(saved);
    } catch {
      /* storage unavailable */
    }
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang === "hi" ? "hi" : "en";
  }, [lang]);

  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* storage unavailable */
    }
  }, []);

  const value = useMemo<I18nValue>(() => {
    const dict = DICTIONARIES[lang];
    return {
      lang,
      setLang,
      dict,
      t: (key, vars) => {
        let text = lookup(dict, key);
        if (vars) for (const [k, v] of Object.entries(vars)) text = text.replaceAll(`{${k}}`, String(v));
        return text;
      },
    };
  }, [lang, setLang]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used inside I18nProvider");
  return ctx;
}
