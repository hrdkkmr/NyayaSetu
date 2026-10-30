"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Toaster } from "sonner";

import { AuthProvider } from "@/lib/auth";
import { I18nProvider } from "@/lib/i18n";
import { ApiError } from "@/lib/api";

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2,
            refetchOnWindowFocus: false,
          },
        },
      }),
  );
  return (
    <QueryClientProvider client={client}>
      <I18nProvider>
        <AuthProvider>
          {children}
          <Toaster richColors position="top-center" closeButton />
        </AuthProvider>
      </I18nProvider>
    </QueryClientProvider>
  );
}
