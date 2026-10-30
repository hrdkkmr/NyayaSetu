"use client";

import { Bell, FileSearch, Gauge, Languages, LogOut, Menu, MessageSquarePlus, Settings, ShieldCheck, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import type { Lang } from "@/lib/types";
import { cn } from "@/lib/utils";

export function Logo({ className }: { className?: string }) {
  const { t } = useI18n();
  return (
    <Link href="/" className={cn("flex items-center gap-2 font-bold text-navy-900", className)}>
      <svg viewBox="0 0 32 32" className="size-8" aria-hidden>
        <rect width="32" height="32" rx="8" fill="#0b2545" />
        <path d="M6 21h20M9 21V13M16 21V10M23 21V13M7 12l9-5 9 5" stroke="#fff" strokeWidth="2" fill="none" strokeLinecap="round" />
        <path d="M6 24h20" stroke="#e0913f" strokeWidth="2" strokeLinecap="round" />
      </svg>
      <span className="text-xl tracking-tight">{t("common.appName")}</span>
    </Link>
  );
}

export function LanguageToggle({ compact = false }: { compact?: boolean }) {
  const { lang, setLang, t } = useI18n();
  const { user, refresh } = useAuth();
  const change = async (next: Lang) => {
    setLang(next);
    if (user) {
      try {
        await api("/users/me/preferences", { method: "PATCH", body: { language: next } });
        await refresh();
      } catch {
        /* language still switches locally */
      }
    }
  };
  return (
    <div role="group" aria-label={t("common.language")} className="flex items-center gap-1 rounded-lg border border-line bg-white p-1">
      {!compact && <Languages className="mx-1 size-4 text-muted" aria-hidden />}
      {(["en", "hi"] as const).map((code) => (
        <button
          key={code}
          type="button"
          onClick={() => change(code)}
          aria-pressed={lang === code}
          className={cn(
            "min-h-8 rounded-md px-2.5 text-sm font-semibold",
            lang === code ? "bg-navy-800 text-white" : "text-navy-800 hover:bg-navy-50",
          )}
        >
          {code === "en" ? "English" : "हिन्दी"}
        </button>
      ))}
    </div>
  );
}

export function PublicHeader() {
  const { t } = useI18n();
  const { user } = useAuth();
  return (
    <header className="border-b border-line bg-white">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3">
        <Logo />
        <div className="flex items-center gap-2">
          <LanguageToggle />
          {user ? (
            <Button asChild size="sm"><Link href="/dashboard">{t("nav.dashboard")}</Link></Button>
          ) : (
            <>
              <Button asChild variant="ghost" size="sm"><Link href="/login">{t("common.signIn")}</Link></Button>
              <Button asChild size="sm" className="hidden sm:inline-flex"><Link href="/register">{t("common.register")}</Link></Button>
            </>
          )}
        </div>
      </div>
    </header>
  );
}

export function Footer() {
  const { t } = useI18n();
  return (
    <footer className="mt-16 border-t border-line bg-white">
      <div className="mx-auto max-w-6xl space-y-3 px-4 py-8 text-sm text-muted">
        <p className="font-semibold text-navy-900">{t("common.appName")} — {t("common.tagline")}</p>
        <p>{t("common.notAdvice")}</p>
        <p>
          NALSA 15100 · {t("landing.catConsumer")}: 1915 · <Link className="underline" href="/privacy">Privacy</Link>
        </p>
      </div>
    </footer>
  );
}

const NAV = [
  { href: "/dashboard", key: "nav.dashboard", icon: Gauge },
  { href: "/cases/new", key: "nav.newCase", icon: MessageSquarePlus },
  { href: "/research", key: "nav.research", icon: FileSearch },
  { href: "/settings", key: "nav.settings", icon: Settings },
] as const;

export function AppShell({ children, unread = 0 }: { children: ReactNode; unread?: number }) {
  const { t } = useI18n();
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const items = user?.role === "admin" ? [...NAV, { href: "/admin", key: "nav.admin" as const, icon: ShieldCheck }] : NAV;

  return (
    <div className="flex min-h-screen flex-col">
      <a href="#main" className="skip-link">{t("common.skipToContent")}</a>
      <header className="sticky top-0 z-30 border-b border-line bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-4 py-2.5">
          <Logo />
          <nav aria-label="Main" className="hidden items-center gap-1 lg:flex">
            {items.map(({ href, key, icon: Icon }) => (
              <Link
                key={href}
                href={href}
                aria-current={pathname.startsWith(href) ? "page" : undefined}
                className={cn(
                  "flex min-h-10 items-center gap-2 rounded-lg px-3 text-sm font-semibold",
                  pathname.startsWith(href) ? "bg-navy-50 text-navy-900" : "text-muted hover:text-navy-900",
                )}
              >
                <Icon className="size-4" aria-hidden />
                {t(key)}
              </Link>
            ))}
          </nav>
          <div className="flex items-center gap-2">
            <LanguageToggle compact />
            <Link href="/dashboard#notifications" className="relative rounded-lg p-2 text-navy-800 hover:bg-navy-50" aria-label={t("nav.notifications")}>
              <Bell className="size-5" />
              {unread > 0 && (
                <span className="absolute -right-0.5 -top-0.5 rounded-full bg-saffron-600 px-1.5 text-xs font-bold text-white">{unread}</span>
              )}
            </Link>
            <Button variant="ghost" size="icon" className="hidden lg:inline-flex" onClick={logout} aria-label={t("common.signOut")}>
              <LogOut />
            </Button>
            <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-label={t("nav.menu")}>
              {open ? <X /> : <Menu />}
            </Button>
          </div>
        </div>
        {open && (
          <nav aria-label="Main mobile" className="border-t border-line bg-white px-4 py-2 lg:hidden">
            {items.map(({ href, key, icon: Icon }) => (
              <Link key={href} href={href} onClick={() => setOpen(false)} className="flex min-h-12 items-center gap-3 rounded-lg px-2 font-semibold text-navy-900 hover:bg-navy-50">
                <Icon className="size-5" aria-hidden /> {t(key)}
              </Link>
            ))}
            <button onClick={logout} className="flex min-h-12 w-full items-center gap-3 rounded-lg px-2 font-semibold text-danger-700 hover:bg-danger-100">
              <LogOut className="size-5" aria-hidden /> {t("common.signOut")}
            </button>
          </nav>
        )}
      </header>
      <main id="main" className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">{children}</main>
      <footer className="border-t border-line bg-white px-4 py-4 text-center text-xs text-muted">{t("common.notAdvice")}</footer>
    </div>
  );
}
