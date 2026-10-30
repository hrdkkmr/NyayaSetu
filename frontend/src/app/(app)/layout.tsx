"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { AppShell } from "@/components/layout";
import { Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Notification } from "@/lib/types";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const { data: unread } = useQuery({
    queryKey: ["notifications", "unread"],
    queryFn: () => api<Notification[]>("/notifications?unread_only=true"),
    enabled: !!user,
    refetchInterval: 60_000,
  });

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <div className="mx-auto max-w-5xl space-y-4 p-6" aria-busy>
        <Skeleton className="h-10 w-48" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }
  return <AppShell unread={unread?.length ?? 0}>{children}</AppShell>;
}
