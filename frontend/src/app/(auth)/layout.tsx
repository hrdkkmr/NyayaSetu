"use client";

import { PublicHeader } from "@/components/layout";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <PublicHeader />
      <main id="main" className="mx-auto flex max-w-md flex-col px-4 py-10">{children}</main>
    </>
  );
}
